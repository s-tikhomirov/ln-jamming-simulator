from queue import PriorityQueue
import networkx as nx

from channel import ChannelDirection, ErrorType, RevenueType
from params import K, M, ProtocolParams
from payment import Payment


def get_channel_graph_from_json(snapshot_json, default_num_slots):
	# Convert a JSON object (scheme: CLN's listchannels) into an UNDIRECTED graph (MultiGraph).
	# Each edge corresponds to a channel. Edge id = channel id.
	# Edge attributes: capacity, directions: [ChannelDirection0, ChannelDirection1]
	g = nx.MultiGraph()
	for cd in snapshot_json["channels"]:
		cid = cd["short_channel_id"]
		capacity = cd["satoshis"]
		src, dst = cd["source"], cd["destination"]
		direction = src < dst
		# Fees may be set manually later in testing snapshots
		upfront_base_fee = cd["base_fee_millisatoshi_upfront"] / K if "base_fee_millisatoshi_upfront" in cd else None
		upfront_fee_rate = cd["fee_per_millionth_upfront"] / M if "fee_per_millionth_upfront" in cd else None
		success_base_fee = cd["base_fee_millisatoshi"] / K if "base_fee_millisatoshi" in cd else None
		success_fee_rate = cd["fee_per_millionth"] / M if "fee_per_millionth" in cd else None
		cd = ChannelDirection(
			is_enabled=cd["active"],
			num_slots=default_num_slots,
			upfront_base_fee=upfront_base_fee,
			upfront_fee_rate=upfront_fee_rate,
			success_base_fee=success_base_fee,
			success_fee_rate=success_fee_rate
		)
		for node in [src, dst]:
			if node not in g.nodes:
				g.add_node(node, upfront_revenue=0, success_revenue=0)
		if src not in g.neighbors(dst):
			g.add_edge(src, dst, cid, capacity=capacity, directions=[None, None])
		else:
			if cid not in (value[2] for value in g.edges(src, dst, keys=True)):
				g.add_edge(src, dst, cid, capacity=capacity, directions=[None, None])
		ch = g[src][dst][cid]
		# if we encounter the same cid in the snapshot, it must have the same capacity
		assert(capacity == ch["capacity"])
		# we shouldn't yet have populated this direction for this cid
		assert(ch["directions"][direction] is None)
		ch["directions"][direction] = cd
	return g


def get_routing_graph_from_json(snapshot_json):
	# Get a DIRECTED graph (MultiDiGraph) for routing from the same JSON object.
	# Each edge corresponds to an enabled (i.e., "active") channel direction.
	# We only parse cid and capacity (it's relevant for routing).
	# All other attributes (fee functions, revenues) are stored in the undirected channel graph.
	g = nx.MultiDiGraph()
	for cd in snapshot_json["channels"]:
		if not cd["active"]:
			continue
		cid = cd["short_channel_id"]
		capacity = cd["satoshis"]
		src, dst = cd["source"], cd["destination"]
		g.add_edge(src, dst, cid, capacity=capacity)
	return g


class LNModel:
	'''
		A class to store the LN graph and do graph operations.
	'''

	def __init__(self, snapshot_json, default_num_slots):
		'''
			- snapshot_json
				A JSON object describing the LN graph (CLN's listchannels).

			- default_num_slots
				Default number of slots in the graph.
		'''
		self.default_num_slots = default_num_slots
		self.channel_graph = get_channel_graph_from_json(snapshot_json, self.default_num_slots)
		self.routing_graph = get_routing_graph_from_json(snapshot_json)
		# To filter graph views, add a safety margin to account for the (yet unknown) fees.
		self.capacity_filtering_safety_margin = 0.05

	def add_revenue(self, node, revenue_type, amount):
		self.channel_graph.nodes[node][revenue_type.value] += amount

	def subtract_revenue(self, node, revenue_type, amount):
		self.add_revenue(node, revenue_type, -amount)

	def get_revenue(self, node, revenue_type):
		return self.channel_graph.nodes[node][revenue_type.value]

	def set_revenue(self, node, revenue_type, amount):
		self.channel_graph.nodes[node][revenue_type.value] = amount

	def get_routing_graph_for_amount(self, amount):
		# Return a graph view that only includes edges with capacity >= amount
		#print("Filtering out edges with capacity < ", amount)
		def filter_edges(n1, n2, cid):
			return self.routing_graph[n1][n2][cid]["capacity"] >= amount
		return nx.subgraph_view(self.routing_graph, lambda _: True, filter_edges)

	def get_routes(self, sender, receiver, amount, must_route_via_nodes=[]):
		# Get a route from sender to (router_1 - router_2 - receiver).
		# In the jamming context, (router_1 - router_2) is the target hop.
		# We assume that the (jammer-)receiver is directly connected to router_2.
		# Although there may be multiple hops from sender to router_1.
		route = None
		is_route_via = (len(must_route_via_nodes) > 0)
		routing_graph = self.get_routing_graph_for_amount(
			amount=(1 + self.capacity_filtering_safety_margin) * amount)
		if not all([n in routing_graph for n in [sender, receiver] + must_route_via_nodes]):
			#print("No route")
			#print("Not in routing graph:", [n for n in [sender, router_1, router_2, receiver] if n not in routing_graph])
			yield from ()
		if is_route_via:
			#print("Finding route via", event.must_route_via)
			router_first = must_route_via_nodes[0]
			router_last = must_route_via_nodes[-1]
			if not nx.has_path(routing_graph, sender, router_first):
				#print("No path from sender", sender, "to router_1", router)
				yield from ()
			elif router_last not in routing_graph.predecessors(receiver):
				#print("No (big enough) channel from", router_2, "to", receiver)
				#print("Note: last router and receiver must be directly connected!")
				yield from ()
			else:
				routes = nx.all_shortest_paths(routing_graph, sender, router_first)
				route = next(routes, None)
		else:
			if not nx.has_path(routing_graph, sender, receiver):
				#print("No route - no path between sender and receiver")
				yield from ()
			else:
				routes = nx.all_shortest_paths(routing_graph, sender, receiver)
				route = next(routes, None)
		while route is not None:
			if is_route_via:
				route.extend(must_route_via_nodes[1:])
				route.append(receiver)
			yield route
			route = next(routes, None)

	def lowest_fee_enabled_channel(self, u_node, d_node, amount, direction):
		channels_dict = self.channel_graph.get_edge_data(u_node, d_node)
		assert(channels_dict is not None), (u_node, d_node)

		def filter_dirs_in_hop(channels_dict, amount, direction, is_suitable):
			# Return only ch_dirs from a hop that are suitable as per is_suitable function.
			suitable_ch_dirs = [
				(cid, ch["directions"][direction]) for cid, ch in channels_dict.items()
				if is_suitable(ch["directions"][direction])]
			return suitable_ch_dirs

		def ch_dir_enabled(ch_dir):
			is_enabled = ch_dir.is_enabled if ch_dir is not None else False
			return is_enabled
		filtered_ch_dirs = filter_dirs_in_hop(channels_dict, amount, direction, is_suitable=ch_dir_enabled)

		def sort_filtered_ch_dirs(filtered_ch_dirs, sorting_function):
			# Sort ch_dirs as per a given sorting function.
			return sorted(filtered_ch_dirs, key=sorting_function)

		def total_fee(ch_dir, amount):
			success_fee = ch_dir.success_fee_function(amount)
			upfront_fee = ch_dir.upfront_fee_function(amount + success_fee)
			return success_fee + upfront_fee
		sorted_filtered_ch_dirs = sort_filtered_ch_dirs(
			filtered_ch_dirs,
			sorting_function=lambda cid_ch_dir: total_fee(cid_ch_dir[1], amount))
		chosen_cid, ch_dir = sorted_filtered_ch_dirs[0]
		return chosen_cid, ch_dir

	def prob_balance_failure(self, u_node, d_node, cid, amount):
		channels_dict = self.channel_graph.get_edge_data(u_node, d_node)
		return amount / channels_dict[cid]["capacity"]

	def create_payment(self, route, amount, processing_delay, desired_result, enforce_dust_limit):
		p, u_nodes, d_nodes = None, route[:-1], route[1:]
		for u_node, d_node in reversed(list(zip(u_nodes, d_nodes))):
			#print("Wrapping payment w.r.t. fee policy of", u_node, d_node)
			#print("Channels in this hop:", list(channels_dict.keys()))
			chosen_cid, chosen_ch_dir = self.lowest_fee_enabled_channel(u_node, d_node, amount, direction=(u_node < d_node))
			#print(chosen_ch_dir)
			is_last_hop = p is None
			p = Payment(
				downstream_payment=p,
				downstream_node=d_node,
				upfront_fee_function=chosen_ch_dir.upfront_fee_function,
				success_fee_function=chosen_ch_dir.success_fee_function,
				desired_result=desired_result if is_last_hop else None,
				processing_delay=processing_delay if is_last_hop else None,
				receiver_amount=amount if is_last_hop else None)
			if enforce_dust_limit:
				assert(p.amount >= ProtocolParams["DUST_LIMIT"]), (p.amount, ProtocolParams["DUST_LIMIT"])
		return p

	def set_fee(self, node_1, node_2, revenue_type, base, rate):
		# Set a fee function of form f(a) = b + ra to the channel between node_1 and node_2.
		# Note: we assume there is at most one channel between the nodes!
		if node_1 not in self.routing_graph.predecessors(node_2):
			print("Can't set fee: no channel between", node_1, node_2)
			pass
		else:
			ch_dir = self.get_only_ch_dir(node_1, node_2)
			ch_dir.set_fee(revenue_type, base, rate)

	def set_fee_for_all(self, revenue_type, base, rate):
		for (node_1, node_2) in self.routing_graph.edges():
			#print("Setting fee", revenue_type.value, "for", node_1, node_2)
			#print("Setting fee", revenue_type.value, "for", node_1, node_2)
			self.set_fee(node_1, node_2, revenue_type, base, rate)

	def set_upfront_fee_from_coeff_for_all(self, upfront_base_coeff, upfront_rate_coeff):
		for (node_1, node_2) in self.routing_graph.edges():
			ch_dir = self.get_only_ch_dir(node_1, node_2)
			ch_dir.set_fee(
				RevenueType.UPFRONT,
				upfront_base_coeff * ch_dir.success_base_fee,
				upfront_rate_coeff * ch_dir.success_fee_rate)

	def set_num_slots(self, node_1, node_2, num_slots):
		# Resize the slots queue to a num_slots.
		# Note: by default, this erases existing in-flight HTLCs.
		# (Which is OK as we use this to reset the graph between experiments.)
		ch_dir = self.get_only_ch_dir(node_1, node_2)
		if ch_dir is not None:
			ch_dir.set_num_slots(num_slots)

	def get_only_ch_dir(self, node_1, node_2):
		ch_dict = self.channel_graph.get_edge_data(node_1, node_2)
		direction = (node_1 < node_2)
		# assume there is only one channel in this hop
		assert(len(ch_dict.keys()) == 1)
		ch_dir = next(iter(ch_dict.values()))["directions"][direction]
		return ch_dir

	def set_deliberate_failure_behavior(self, node_1, node_2, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		ch_dir = self.get_only_ch_dir(node_1, node_2)
		ch_dir.deliberately_fail_prob = prob
		ch_dir.spoofing_error_type = spoofing_error_type

	def report_revenues(self):
		print("\n\n*** Revenues ***")
		for node in self.channel_graph.nodes:
			success_revenue = self.get_revenue(node, RevenueType.SUCCESS)
			upfront_revenue = self.get_revenue(node, RevenueType.UPFRONT)
			print("\n", node)
			print("Upfront:", upfront_revenue)
			print("Success:", success_revenue)
			print("Total:", upfront_revenue + success_revenue)

	def reset_revenues(self):
		#print("Resetting revenues")
		for node in self.channel_graph.nodes:
			self.set_revenue(node, RevenueType.SUCCESS, 0)
			self.set_revenue(node, RevenueType.UPFRONT, 0)

	def reset_in_flight_htlcs(self):
		#print("Resetting in-flight HTLCs")
		for node_1, node_2 in self.routing_graph.edges():
			ch_dict = self.channel_graph.get_edge_data(node_1, node_2)
			direction = (node_1 < node_2)
			for cid in ch_dict:
				ch_dir = ch_dict[cid]["directions"][direction]
				if ch_dir is not None:
					ch_dir.slots = PriorityQueue(maxsize=ch_dir.num_slots)

	def reset(self):
		self.reset_revenues()
		self.reset_in_flight_htlcs()

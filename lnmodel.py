from queue import PriorityQueue
import networkx as nx
from random import choice
from string import digits

from channel import ChannelDirection, ErrorType, FeeType
from params import K, M, ProtocolParams
from payment import Payment

import logging
logger = logging.getLogger(__name__)


class LNModel:
	'''
		A class to store the LN graph and do graph operations.
	'''

	def __init__(self, snapshot_json, default_num_slots, capacity_filtering_safety_margin=0.05):
		'''
			- snapshot_json
				A JSON object describing the LN graph (CLN's listchannels).

			- default_num_slots
				Default number of slots in the graph.

			- capacity_filtering_safety_margin
				An extra allowed capacity allowed when filtering graph for sending a given amount.
		'''
		logger.debug(f"Initializing LNModel with {default_num_slots} slots per channel direction")
		self.default_num_slots = default_num_slots
		self.get_graphs_from_json(snapshot_json)
		# To filter graph views, add a safety margin to account for the (yet unknown) fees.
		self.capacity_filtering_safety_margin = capacity_filtering_safety_margin

	def get_graphs_from_json(self, snapshot_json):
		# Channel graph is an UNDIRECTED graph (MultiGraph).
		# Each edge corresponds to a channel. Edge id = channel id.
		# Edge attributes: capacity, directions: [ChannelDirection0, ChannelDirection1]
		self.channel_graph = nx.MultiGraph()
		# Routing graph is a DIRECTED graph (MultiDiGraph) from the same JSON object.
		# Each edge corresponds to an enabled (i.e., "active") channel direction.
		# We only parse cid and capacity (it's relevant for routing).
		# All other attributes (fee functions, revenues) are stored in the undirected channel graph.
		self.routing_graph = nx.MultiDiGraph()
		for cd in snapshot_json["channels"]:
			src, dst, capacity, cid, is_enabled = cd["source"], cd["destination"], cd["satoshis"], cd["short_channel_id"], cd["active"]
			upfront_base_fee = cd["base_fee_millisatoshi_upfront"] / K if "base_fee_millisatoshi_upfront" in cd else None
			upfront_fee_rate = cd["fee_per_millionth_upfront"] / M if "fee_per_millionth_upfront" in cd else None
			success_base_fee = cd["base_fee_millisatoshi"] / K if "base_fee_millisatoshi" in cd else None
			success_fee_rate = cd["fee_per_millionth"] / M if "fee_per_millionth" in cd else None
			self.add_edge(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, is_enabled)
		self.reset_revenues_for_all()

	def add_edge(
		self,
		src,
		dst,
		capacity,
		cid=None,
		upfront_base_fee=0,
		upfront_fee_rate=0,
		success_base_fee=0,
		success_fee_rate=0,
		is_enabled=True,
		num_slots_multiplier=1):
		if cid is None:
			cid = src[:1] + dst[:1] + "x" + "".join(choice(digits) for i in range(4))
		self.add_edge_to_channel_graph(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, is_enabled, num_slots_multiplier)
		if is_enabled:
			self.add_edge_to_routing_graph(src, dst, capacity, cid)

	def add_edge_to_channel_graph(self, src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, is_enabled, num_slots_multiplier):
		cd = ChannelDirection(
			is_enabled=is_enabled,
			num_slots=num_slots_multiplier * self.default_num_slots,
			upfront_base_fee=upfront_base_fee,
			upfront_fee_rate=upfront_fee_rate,
			success_base_fee=success_base_fee,
			success_fee_rate=success_fee_rate
		)
		for node in (src, dst):
			self.channel_graph.add_node(node)
			self.reset_revenue(node)
		if src not in self.channel_graph.neighbors(dst) or cid not in self.channel_graph.get_edge_data(src, dst):
			self.channel_graph.add_edge(src, dst, cid, capacity=capacity, directions=[None, None])
		ch = self.channel_graph[src][dst][cid]
		# if we encounter the same cid in the snapshot, it must have the same capacity
		assert(capacity == ch["capacity"])
		direction = src < dst
		# we shouldn't yet have populated this direction for this cid
		assert(ch["directions"][direction] is None)
		ch["directions"][direction] = cd

	def add_edge_to_routing_graph(self, src, dst, capacity, cid):
		self.routing_graph.add_edge(src, dst, cid, capacity=capacity, cid=cid)

	def add_jammers_channels(
		self,
		send_to,
		receive_from,
		capacity=1000000,
		num_slots_multiplier=2):
		for node in send_to:
			self.add_edge(
				src="JammerSender",
				dst=node,
				capacity=capacity,
				num_slots_multiplier=num_slots_multiplier)
		for node in receive_from:
			self.add_edge(
				src=node,
				dst="JammerReceiver",
				capacity=capacity,
				num_slots_multiplier=num_slots_multiplier)

	def add_revenue(self, node, fee_type, amount):
		self.channel_graph.nodes[node][fee_type.value] += amount

	def subtract_revenue(self, node, fee_type, amount):
		self.add_revenue(node, fee_type, -amount)

	def get_revenue(self, node, fee_type):
		return self.channel_graph.nodes[node][fee_type.value]

	def reset_revenue(self, node):
		self.channel_graph.nodes[node][FeeType.UPFRONT.value] = 0
		self.channel_graph.nodes[node][FeeType.SUCCESS.value] = 0

	def reset_revenues_for_all(self):
		logger.debug("Resetting all revenues")
		for node in self.channel_graph.nodes:
			self.reset_revenue(node)

	def get_routing_graph_for_amount(self, amount):
		# Return a graph view that only includes edges with capacity >= amount
		def filter_edges(n1, n2, cid):
			return self.routing_graph[n1][n2][cid]["capacity"] >= amount
		logger.debug(f"Filtering out edges with capacity < {amount}")
		return nx.subgraph_view(self.routing_graph, lambda _: True, filter_edges)

	def get_routes(self, sender, receiver, amount, must_route_via_nodes=[]):
		# Get a route from sender to (router_1 - router_2 - receiver).
		# In the jamming context, (router_1 - router_2) is the target hop.
		# We assume that the (jammer-)receiver is directly connected to router_2.
		# Although there may be multiple hops from sender to router_1.
		route = None
		is_route_via = (len(must_route_via_nodes) > 0)
		logger.debug(f"Finding route from {sender} to {receiver}" + (f" via {must_route_via_nodes}" if is_route_via else ""))
		routing_graph = self.get_routing_graph_for_amount(
			amount=(1 + self.capacity_filtering_safety_margin) * amount)
		if not all([n in routing_graph for n in [sender, receiver] + must_route_via_nodes]):
			not_in_routing_graph = [n for n in [sender, receiver] + must_route_via_nodes if n not in routing_graph]
			logger.warning(f"Can't find route from {sender} to {receiver} via {must_route_via_nodes} nodes {not_in_routing_graph} are not in the routing graph")
			yield from ()
		if is_route_via:
			router_first = must_route_via_nodes[0]
			router_last = must_route_via_nodes[-1]
			if not nx.has_path(routing_graph, sender, router_first):
				logger.warning(f"No path from {sender} to {router_first}")
				yield from ()
			elif router_last not in routing_graph.predecessors(receiver):
				logger.warning(f"No (big enough) channel from {router_last} to {receiver}")
				logger.warning(f"Note: last router and receiver must be directly connected!")
				yield from ()
			else:
				routes = nx.all_shortest_paths(routing_graph, sender, router_first)
				route = next(routes, None)
		else:
			if not nx.has_path(routing_graph, sender, receiver):
				logger.warning(f"No path from {sender} to {receiver}")
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
			chosen_cid, chosen_ch_dir = self.lowest_fee_enabled_channel(u_node, d_node, amount, direction=(u_node < d_node))
			logger.debug(f"Wrapping payment for fee policy in {chosen_cid} from {u_node} to {d_node}")
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

	def set_fee(self, u_node, d_node, fee_type, base, rate):
		# Set a fee function of form f(a) = b + ra to the channel between u_node and d_node.
		# Note: we assume there is at most one channel between the nodes!
		logger.debug(f"Setting {fee_type.value} fee from {u_node} to {d_node} to: base {base}, rate {rate}")
		if u_node not in self.routing_graph.predecessors(d_node):
			logger.debug(f"Can't set fee: no channel from {u_node} to {d_node}")
			pass
		else:
			ch_dir = self.get_only_ch_dir(u_node, d_node)
			ch_dir.set_fee(fee_type, base, rate)

	def set_fee_for_all(self, fee_type, base, rate):
		logger.debug(f"Setting {fee_type.value} fee for all to: base {base}, rate {rate}")
		for (u_node, d_node) in self.routing_graph.edges():
			self.set_fee(u_node, d_node, fee_type, base, rate)

	def set_upfront_fee_from_coeff_for_all(self, upfront_base_coeff, upfront_rate_coeff):
		for (u_node, d_node) in self.routing_graph.edges():
			ch_dir = self.get_only_ch_dir(u_node, d_node)
			ch_dir.set_fee(
				FeeType.UPFRONT,
				upfront_base_coeff * ch_dir.success_base_fee,
				upfront_rate_coeff * ch_dir.success_fee_rate)

	def set_num_slots(self, u_node, d_node, num_slots):
		# Resize the slots queue to a num_slots.
		# Note: by default, this erases existing in-flight HTLCs.
		# (Which is OK as we use this to reset the graph between experiments.)
		ch_dir = self.get_only_ch_dir(u_node, d_node)
		if ch_dir is not None:
			ch_dir.set_num_slots(num_slots)

	def get_only_ch_dir(self, u_node, d_node):
		ch_dict = self.channel_graph.get_edge_data(u_node, d_node)
		direction = (u_node < d_node)
		# assume there is only one channel in this hop
		assert(len(ch_dict.keys()) == 1)
		ch_dir = next(iter(ch_dict.values()))["directions"][direction]
		return ch_dir

	def set_deliberate_failure_behavior(self, u_node, d_node, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		ch_dir = self.get_only_ch_dir(u_node, d_node)
		ch_dir.deliberately_fail_prob = prob
		ch_dir.spoofing_error_type = spoofing_error_type

	def report_revenues(self):
		print("\n\n*** Revenues ***")
		for node in self.channel_graph.nodes:
			success_revenue = self.get_revenue(node, FeeType.SUCCESS)
			upfront_revenue = self.get_revenue(node, FeeType.UPFRONT)
			print("\n", node)
			print("Upfront:", upfront_revenue)
			print("Success:", success_revenue)
			print("Total:", upfront_revenue + success_revenue)

	def reset_in_flight_htlcs(self):
		logger.debug("Resetting all in-flight HTLCs")
		for u_node, d_node in self.routing_graph.edges():
			ch_dict = self.channel_graph.get_edge_data(u_node, d_node)
			direction = (u_node < d_node)
			for cid in ch_dict:
				ch_dir = ch_dict[cid]["directions"][direction]
				if ch_dir is not None:
					ch_dir.slots = PriorityQueue(maxsize=ch_dir.num_slots)

	def reset(self):
		self.reset_revenues_for_all()
		self.reset_in_flight_htlcs()

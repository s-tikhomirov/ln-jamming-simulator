import networkx as nx
import json
from functools import partial
from queue import PriorityQueue

from channel import ChannelDirection, dir0, dir1
from params import K, M

from enum import Enum

TEST_NUM_SLOTS = 2

class RevenueType(Enum):
	UPFRONT = "upfront_revenue"
	SUCCESS = "success_revenue"

def get_channel_graph_from_json(snapshot_json, default_num_slots = TEST_NUM_SLOTS):
	# Parse a Core Lightning listchannels.json snapshot
	# into a NetworkX MultiGraph.
	# Each edge corresponds to a channel. Edge id = channel id.
	# Edge attributes: capacity, directions : [ChannelDirection0, ChannelDirection1]
	g = nx.MultiGraph()
	for cd in snapshot_json["channels"]:
		cid = cd["short_channel_id"]
		capacity = cd["satoshis"]
		src, dst = cd["source"], cd["destination"]
		direction = src < dst
		# Fees may be set manually later in testing snapshots
		base_fee_success = cd["base_fee_millisatoshi"] / K 			if "base_fee_millisatoshi" in cd else None
		fee_rate_success = cd["fee_per_millionth"] / M 				if "fee_per_millionth" in cd else None
		base_fee_upfront = cd["base_fee_millisatoshi_upfront"] / K 	if "base_fee_millisatoshi_upfront" in cd else None
		fee_rate_upfront = cd["fee_per_millionth_upfront"] / M 		if "fee_per_millionth_upfront" in cd else None
		cd = ChannelDirection(
			is_enabled = cd["active"],
			num_slots = default_num_slots,
			upfront_fee_function = partial(lambda b, r, a : b + r * a, base_fee_upfront, fee_rate_upfront),
			success_fee_function = partial(lambda b, r, a : b + r * a, base_fee_success, fee_rate_success)
			)
		for node in [src, dst]:
			if node not in g.nodes:
				g.add_node(node, upfront_revenue=0, success_revenue=0)
		if src not in g.neighbors(dst):
			g.add_edge(src, dst, cid, capacity=capacity, directions = [None, None])
		else:
			if cid not in (value[2] for value in g.edges(src, dst, keys=True)):
				g.add_edge(src, dst, cid, capacity=capacity, directions = [None, None])
		ch = g[src][dst][cid]
		# if we encounter the same cid in the snapshot, it must have the same capacity
		assert(capacity == ch["capacity"])
		# we shouldn't yet have populated this direction for this cid
		assert(ch["directions"][direction] is None)
		ch["directions"][direction] = cd
	return g

def get_routing_graph_from_json(snapshot_json):
	# Get a DIRECTED MULTI-graph from the same JSON for routing.
	# Each edge corresponds to an enabled (i.e., "active") channel direction.
	# We only parse cid and capacity (it's relevant for routing).
	# All other attributes (fee functions, revenues) are stored in the channel graph.
	g = nx.MultiDiGraph()
	for cd in snapshot_json["channels"]:
		if cd["active"] == False:
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

	def __init__(self, snapshot_json, default_num_slots=TEST_NUM_SLOTS):
		self.channel_graph = get_channel_graph_from_json(snapshot_json, default_num_slots)
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
		return nx.subgraph_view(self.routing_graph, lambda _:True, filter_edges)

	def get_routes(self, sender, receiver, amount):
		# A routes iterator for a given amount from sender to receiver
		routing_graph = self.get_routing_graph_for_amount(
			amount=(1 + self.capacity_filtering_safety_margin) * amount)
		#print("Routing graph has nodes:", list(routing_graph.nodes()))
		#print("Searching for route from", sender, "to", receiver, "for", amount)
		if sender not in routing_graph or receiver not in routing_graph:
			#print("No route - sender or receiver not in routing graph")
			yield from ()
		elif not nx.has_path(routing_graph, sender, receiver):
			#print("No route - no path between sender and receiver")
			yield from ()
		else:
			routes = nx.all_shortest_paths(routing_graph, sender, receiver)
			route = next(routes, None)
			while route != None:
				#print("Yielding", route)
				yield route
				route = next(routes, None)

	def get_routes_via_hop(self, sender, router_1, router_2, receiver, amount):
		# Get a route from sender to (router_1 - router_2 - receiver).
		# In the jamming context, (router_1 - router_2) is the target hop.
		# We assume that the (jammer-)receiver is directly connected to router_2.
		# Although there may be multiple hops from sender to router_1.
		routing_graph = self.get_routing_graph_for_amount(
			amount=(1 + self.capacity_filtering_safety_margin) * amount)
		if not all([n in routing_graph for n in [sender, router_1, router_2, receiver]]):
			#print("No route")
			#print("Not in routing graph:", [n for n in [sender, router_1, router_2, receiver] if n not in routing_graph])
			yield from ()
		elif not nx.has_path(routing_graph, sender, router_1):
			#print("No path from sender", sender, "to router_1", router)
			yield from ()
		elif not router_1 in routing_graph.predecessors(router_2):
			#print("No (big enough) channel from", router_1, "to", router_2)
			yield from ()
		elif not router_2 in routing_graph.predecessors(receiver):
			#print("No (big enough) channel from", router_2, "to", receiver)
			yield from ()
		else:
			routes_to_router = nx.all_shortest_paths(routing_graph, sender, router_1)
			route = next(routes_to_router, None)
			while route != None:
				route.append(router_2)
				route.append(receiver)
				yield route
				route = next(routes_to_router, None)

	def set_fee_function(self, node_1, node_2, revenue_type, base, rate):
		# Set a fee function of form f(a) = b + ra to the channel between node_1 and node_2.
		# Note: we assume there is at most one channel between the nodes!
		if not node_1 in self.channel_graph.neighbors(node_2):
			#print("Can't set fee: no channel between", node_1, node_2)
			pass
		else:
			ch_dict = self.channel_graph.get_edge_data(node_1, node_2)
			direction = node_1 < node_2
			assert(len(ch_dict.keys()) == 1)
			ch_dir = next(iter(ch_dict.values()))["directions"][direction]
			fee_function = partial(lambda b, r, a : b + r * a, base, rate)
			if revenue_type == RevenueType.UPFRONT:
				ch_dir.upfront_fee_function = fee_function
			elif revenue_type == RevenueType.SUCCESS:
				ch_dir.success_fee_function = fee_function
			else:
				#print("Unexpected fee type! Can't set fee.")
				pass

	def set_fee_function_for_all(self, revenue_type, base, rate):
		for (node_1, node_2) in self.channel_graph.edges():
			self.set_fee_function(node_1, node_2, revenue_type, base, rate)

	def set_num_slots(self, node_1, node_2, num_slots):
		# Resize the slots queue to a num_slots.
		# Note: by default, this erases existing in-flight HTLCs.
		# (Which is OK as we use this to reset the graph between experiments.)
		ch_dict = self.channel_graph.get_edge_data(node_1, node_2)
		direction = (node_1 < node_2)
		# assume there is only one channel in this hop
		assert(len(ch_dict.keys()) == 1)
		ch_dir = next(iter(ch_dict.values()))["directions"][direction]
		if ch_dir is not None:
			ch_dir.set_num_slots(num_slots)

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

	def reset_in_flight_htlcs(self, default_num_slots):
		#print("Resetting in-flight HTLCs")
		for node_1, node_2 in self.channel_graph.edges():
			ch_dict = self.channel_graph.get_edge_data(node_1, node_2)
			direction = (node_1 < node_2)
			for cid in ch_dict:
				ch_dir = ch_dict[cid]["directions"][direction]
				if ch_dir is not None:
					ch_dir.slots = PriorityQueue(maxsize=default_num_slots)

	def reset(self, default_num_slots):
		self.reset_revenues()
		self.reset_in_flight_htlcs(default_num_slots)

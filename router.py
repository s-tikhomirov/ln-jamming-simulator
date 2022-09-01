from params import ProtocolParams

import networkx as nx
import itertools

import logging
logger = logging.getLogger(__name__)


class Router:

	def __init__(self, ln_model, amount, max_route_length=ProtocolParams["MAX_ROUTE_LENGTH"]):
		self.ln_model = ln_model
		self.g = nx.MultiDiGraph(ln_model.get_routing_graph_for_amount(
			amount=(1 + ln_model.capacity_filtering_safety_margin) * amount))
		self.max_route_length = max_route_length

	def remove_hop(self, hop):
		self.g.remove_edge(hop[0], hop[1])

	def get_routes_via_target_hops(self, sender, receiver, target_hops, min_target_hops_per_route, max_target_hops_per_route):
		self.target_hops = target_hops

		# CHECK WHETHER ALL TARGET HOPS ARE REACHABLE
		# FIXME: this doesn't work for the wheel experiment (hard-coded route version)
		for hop in target_hops:
			if not nx.has_path(self.g, sender, hop[0]):
				logger.error(f"Can't jam target hop {hop}: node {hop[0]} is unreachable from {sender}!")
				exit()
			if not nx.has_path(self.g, hop[1], receiver):
				logger.error(f"Can't jam target hop {hop}: node {hop[1]} is unreachable towards {receiver}!")
				exit()

		# try to get any route via max target hops
		# if not possible, decrease num target hops per route
		# until it hits 1 or a route is found
		target_hops_per_route = max_target_hops_per_route
		while target_hops_per_route >= min_target_hops_per_route:
			logger.debug(f"\n\n\nLooking for routes with {target_hops_per_route} target hops")
			route = yield from self.get_routes_via_target_hops_subset_of_size(sender, receiver, target_hops_per_route)
			if route is not None:
				logger.debug(f"yielding {[n for n in route]}")
				yield route
			else:
				target_hops_per_route -= 1
		#yield from ()

	def get_routes_via_target_hops_subset_of_size(self, sender, receiver, target_hops_per_route):
		'''
			Create a generator that yield routes that touch as many of the must-route edges as possible.
			This is useful in the jamming context for the jammer to optimize the attack.
			The general idea is to iterate over all subsets of edges.
			The number of all subsets explodes but we hop we would only need a small fraction of them.
		'''
		logger.debug(f"Generating routes via {self.target_hops} with {target_hops_per_route} target hops per route...")

		for target_hops_subset in itertools.combinations(self.target_hops, target_hops_per_route):
			for hops_permutation in itertools.permutations(target_hops_subset):
				logger.debug(f"\n\nConsidering permutation {hops_permutation}")
				logger.debug(f"self.g has {self.g.number_of_edges()} edges")
				# PRE-CALCULATE PATHS FROM SENDER TO EVERYONE AND FROM EVERYONE TO RECEIVER
				# TODO: figure out why we can't pre-calcuate this in a more outer loop
				# (the results are wrong then!)
				self.paths_from_sender = nx.shortest_path(self.g, source=sender)
				self.paths_to_receiver = nx.shortest_path(self.g, target=receiver)
				#logger.debug(f"{self.paths_from_sender}")
				#logger.debug(f"{self.paths_to_receiver}")
				route = self.get_route_via_hops(hops_permutation)
				if route is not None:
					assert(route[0] == sender)
					assert(route[-1] == receiver)
					yield route
				else:
					logger.debug(f"No route for this permutation")
					yield from ()
		#yield from ()

	def get_route_via_hops(self, hops_permutation):
		prev_d_node = None
		for (u_node, d_node) in hops_permutation:
			if not self.g.has_edge(u_node, d_node):
				return None
			if prev_d_node is None:
				route = self.paths_from_sender[hops_permutation[0][0]]
				logger.debug(f"Initial route to {hops_permutation[0][0]} is {route}")
			else:
				if not nx.has_path(self.g, prev_d_node, u_node):
					logger.debug(f"No PATH from previous d_node {prev_d_node} to {u_node}")
					return
				elif prev_d_node != u_node:
					subroute = nx.shortest_path(self.g, prev_d_node, u_node)[1:]
					logger.debug(f"Sub-route from {prev_d_node} to {u_node} is: {subroute}")
					'''
					if not self.g.has_edge(route[-1], subroute[0]):
						logger.debug(f"No edge from the end of route {route[-1]} to the start of subroute {subroute[0]}")
						return None
					'''
					route.extend(subroute)
					logger.debug(f"Route now is {route}")
			# FIXME: test this properly
			if len(route) > self.max_route_length:
				logger.debug(f"Route {route} too long, skipping")
				return None
			logger.debug(f"Appending d_node {d_node}")
			route.append(d_node)
			logger.debug(f"Route now is {route}")
			prev_d_node = d_node
		path_to_receiver = self.paths_to_receiver[prev_d_node]
		logger.debug(f"path to receiver: {path_to_receiver}")
		logger.debug(f"Appending {path_to_receiver[1:]}")
		route.extend(path_to_receiver[1:])
		logger.debug(f"Yielding {route}")
		return route

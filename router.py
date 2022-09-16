import networkx as nx
import itertools

from params import ProtocolParams

import logging
logger = logging.getLogger(__name__)


class Router:

	def __init__(self, ln_model, amount, sender, receiver, max_target_node_pairs_per_route=None, max_route_length=None):
		self.ln_model = ln_model
		self.g = nx.MultiDiGraph(ln_model.get_routing_graph_for_amount(amount))
		self.sender = sender
		self.receiver = receiver
		self.max_route_length = ProtocolParams["MAX_ROUTE_LENGTH"] if max_route_length is None else max_route_length
		max_route_length_minus_two = self.max_route_length - 2
		self.max_target_node_pairs_per_route = max_route_length_minus_two if max_target_node_pairs_per_route is None else max(1, min(max_target_node_pairs_per_route, self.max_route_length - 2))
		assert(self.max_target_node_pairs_per_route > 0)
		self.update_route_generator(target_node_pairs=[], allow_repeated_hops=True)

	def update_route_generator(self, target_node_pairs, max_route_length=None, allow_repeated_hops=True):
		self.target_node_pairs = target_node_pairs
		if target_node_pairs:
			self.max_target_node_pairs_per_route = min(self.max_target_node_pairs_per_route, len(self.target_node_pairs))
		if max_route_length is not None:
			self.max_route_length = max_route_length
			self.max_target_node_pairs_per_route = min(self.max_target_node_pairs_per_route, self.max_route_length)
		self.allow_repeated_hops = allow_repeated_hops
		self.pre_calculate_paths(self.sender, self.receiver)
		self.routes = self.get_routes_via_target_node_pairs()

	def pre_calculate_paths(self, sender, receiver):
		self.paths_from_sender = nx.shortest_path(self.g, source=sender)
		self.paths_to_receiver = nx.shortest_path(self.g, target=receiver)
		for hop in self.target_node_pairs:
			if not nx.has_path(self.g, self.sender, hop[0]):
				self.paths_from_sender[hop[0]] = None
			if not nx.has_path(self.g, hop[1], self.receiver):
				self.paths_to_receiver[hop[1]] = None

	def get_route(self):
		return next(self.routes)

	def remove_hop(self, hop):
		self.g.remove_edge(hop[0], hop[1])

	def get_routes_via_target_node_pairs(self, min_target_node_pairs_per_route=1):
		found_routes = set()
		target_node_pairs_per_route = self.max_target_node_pairs_per_route
		while target_node_pairs_per_route >= min_target_node_pairs_per_route:
			#logger.debug(f"Looking for routes with {target_node_pairs_per_route} target node pairs")
			for target_node_pairs_subset in itertools.combinations(self.target_node_pairs, target_node_pairs_per_route):
				#logger.debug(f"Generating routes via permutation of length {len(target_node_pairs_subset)}...")
				for hops_permutation in itertools.permutations(target_node_pairs_subset):
					#logger.debug(f"Considering permutation {hops_permutation}")
					route = self.get_shortest_route_via_hops(hops_permutation)
					if route is not None:
						#logger.debug(f"Found route of length {len(route)}")
						if route in found_routes:
							#logger.info(f"Route already found, skipping")
							continue
						else:
							found_routes.add(route)
							yield route
			target_node_pairs_per_route -= 1

	def is_suitable(self, route):
		if len(route) > self.max_route_length:
			#logger.debug(f"Route {route} too long (length {len(route)} > {self.max_route_length}), discarding")
			return False
		if Router.has_repeated_hop(route) and not self.allow_repeated_hops:
			#logger.debug(f"Route {route} has repeated hop, discarding")
			return False
		return True

	def get_shortest_route_via_hops(self, hops_permutation):
		# TODO: should we return one route, or yield multiple routes if possible via a given permutation?
		#logger.debug(f"Searching for route from {self.sender} to {self.receiver} via {hops_permutation}")
		prev_d_node = None
		for i, (u_node, d_node) in enumerate(hops_permutation):
			assert self.g.has_edge(u_node, d_node), (u_node, d_node)
			if prev_d_node is None:
				first_hop_first_node = hops_permutation[0][0]
				if self.paths_from_sender[first_hop_first_node] is None:
					return None
				route = self.paths_from_sender[first_hop_first_node].copy()
				#logger.debug(f"Initial route to {first_hop_first_node} is {route}")
				assert(route[0] == self.sender and route[-1] == first_hop_first_node)
			else:
				if not nx.has_path(self.g, prev_d_node, u_node):
					#logger.debug(f"No path from {prev_d_node} to {u_node}")
					return None
				elif prev_d_node != u_node:
					subroute = nx.shortest_path(self.g, prev_d_node, u_node)[1:]
					#logger.debug(f"Sub-route from {prev_d_node} to {u_node} is: {subroute}")
					route.extend(subroute)
					#logger.debug(f"Route of length {len(route)} now is {route}")
			#logger.debug(f"Appending d_node {d_node}")
			route.append(d_node)
			#logger.debug(f"Route of length {len(route)} now is {route}")
			if not self.is_suitable(route):
				return None
			prev_d_node = d_node
		if self.paths_to_receiver[prev_d_node] is None:
			return None
		path_to_receiver = self.paths_to_receiver[prev_d_node]
		#logger.debug(f"path to receiver: {path_to_receiver}")
		#logger.debug(f"Appending {path_to_receiver[1:]}")
		route.extend(path_to_receiver[1:])
		if not self.is_suitable(route):
			return None
		assert(route[0] == self.sender and route[-1] == self.receiver)
		#logger.debug(f"Returning {route}")
		assert(self.allow_repeated_hops or not Router.has_repeated_hop(route))
		return tuple(route)

	@staticmethod
	def get_hops(route):
		return zip(route, route[1:])

	@staticmethod
	def first_permutation_element_index_not_in_path(permutation, route):
		if not permutation:
			return None
		current_hop, i = permutation[0], 0
		for route_hop in Router.get_hops(route):
			if route_hop == current_hop:
				if i == len(permutation) - 1:
					#logger.debug(f"Last hop {route_hop} at position {i} is in route")
					return None
				else:
					i += 1
					current_hop = permutation[i]
					#logger.debug(f"Current hop {route_hop} at position {i} is in route")
		return i

	@staticmethod
	def is_permutation_in_path(permutation, route):
		i = Router.first_permutation_element_index_not_in_path(permutation, route)
		return i is None

	@staticmethod
	def is_hop_in_path(hop, route):
		for route_hop in Router.get_hops(route):
			if route_hop == hop:
				return True
		return False

	@staticmethod
	def has_repeated_hop(route):
		hops = list(zip(route, route[1:]))
		return len(hops) > len(set(hops))

	@staticmethod
	def num_hop_occurs_in_path(hop, route):
		return sum(1 for route_hop in Router.get_hops(route) if route_hop == hop)

	@staticmethod
	def shorten_ids(route, length=6):
		return [node[:length] for node in route]

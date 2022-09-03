from params import ProtocolParams

import networkx as nx
import itertools

import logging
logger = logging.getLogger(__name__)


class Router:

	def __init__(self, ln_model, amount, sender, receiver, max_route_length=ProtocolParams["MAX_ROUTE_LENGTH"]):
		self.ln_model = ln_model
		self.g = nx.MultiDiGraph(ln_model.get_routing_graph_for_amount(
			amount=(1 + ln_model.capacity_filtering_safety_margin) * amount))
		self.max_route_length = max_route_length
		self.sender = sender
		self.receiver = receiver
		self.pre_calculate_paths(sender, receiver)

	def pre_calculate_paths(self, sender, receiver):
		self.paths_from_sender = nx.shortest_path(self.g, source=sender)
		self.paths_to_receiver = nx.shortest_path(self.g, target=receiver)

	def get_path_from_sender(self, node):
		return self.paths_from_sender[node]

	def get_path_from_receiver(self, node):
		return self.paths_to_receiver[node]

	@staticmethod
	def is_hop_in_path(target_hop, path):
		for hop in zip(path, path[1:]):
			if hop == target_hop:
				return True
		return False

	@staticmethod
	def is_permutation_in_path(permutation, path):
		i = Router.first_permutation_element_index_not_in_path(permutation, path)
		return i is None

	def first_permutation_element_index_not_in_path(permutation, path):
		if not permutation:
			return None
		current_hop, i = permutation[0], 0
		for hop in zip(path, path[1:]):
			if hop == current_hop:
				if i == len(permutation) - 1:
					#logger.debug(f"Last hop {hop} at position {i} is in path")
					return None
				else:
					i += 1
					current_hop = permutation[i]
					#logger.debug(f"Current hop {hop} at position {i} is in path")
		return i

	def remove_hop(self, hop):
		self.g.remove_edge(hop[0], hop[1])

	def get_routes_via_target_hops(self, target_hops, min_target_hops_per_route, max_target_hops_per_route, max_route_length=None):
		if max_route_length is None:
			max_route_length = self.max_route_length
		for hop in target_hops:
			if not nx.has_path(self.g, self.sender, hop[0]):
				logger.error(f"Can't jam target hop {hop}: node {hop[0]} is unreachable from {self.sender}!")
				exit()
			if not nx.has_path(self.g, hop[1], self.receiver):
				logger.error(f"Can't jam target hop {hop}: node {hop[1]} is unreachable towards {self.receiver}!")
				exit()
		found_routes = set()
		target_hops_per_route = min(max_target_hops_per_route, len(target_hops))
		while target_hops_per_route >= min_target_hops_per_route:
			logger.debug(f"Looking for routes with {target_hops_per_route} target hops")
			for target_hops_subset in itertools.combinations(target_hops, target_hops_per_route):
				logger.debug(f"Generating routes via permutations of {target_hops_subset}...")
				for hops_permutation in itertools.permutations(target_hops_subset):
					logger.debug(f"Considering permutation {hops_permutation}")
					route = self.get_route_via_hops(hops_permutation, max_route_length)
					if route is not None:
						if route not in found_routes:
							found_routes.add(route)
							yield route
						else:
							logger.debug(f"Route {route} already found")
					else:
						logger.debug(f"No route for this permutation")
						continue
				logger.debug(f"No routes for this target_hops_subset")
				continue
			target_hops_per_route -= 1

	def get_route_via_hops(self, hops_permutation, max_route_length=None):
		# TODO: should we return one route, or yield multiple routes if possible via a given permutation?
		if max_route_length is None:
			max_route_length = self.max_route_length
		logger.debug(f"Searching for route from {self.sender} to {self.receiver} via {hops_permutation}")
		prev_d_node, skip_hops = None, 0
		for i, (u_node, d_node) in enumerate(hops_permutation):
			if not self.g.has_edge(u_node, d_node):
				return None
			if skip_hops > 0:
				skip_hops -= 1
				continue
			if prev_d_node is None:
				first_hop_first_node = hops_permutation[0][0]
				route = self.paths_from_sender[first_hop_first_node].copy()
				logger.debug(f"Initial route to {first_hop_first_node} is {route}")
				assert(route[0] == self.sender and route[-1] == first_hop_first_node)
			else:
				j = Router.first_permutation_element_index_not_in_path(hops_permutation, route)
				if j > i:
					logger.debug(f"We are considering hop number {i}")
					logger.debug(f"But the first hop in permutation that is NOT in route is {j}")
					logger.debug(f"We may jump to index {j} right away!")
					skip_hops = j - i
					continue
				elif not nx.has_path(self.g, prev_d_node, u_node):
					logger.debug(f"No path from {prev_d_node} to {u_node}")
					return None
				elif prev_d_node != u_node:
					subroute = nx.shortest_path(self.g, prev_d_node, u_node)[1:]
					#logger.debug(f"Sub-route from {prev_d_node} to {u_node} is: {subroute}")
					route.extend(subroute)
					#logger.debug(f"Route of length {len(route)} now is {route}")
			#logger.debug(f"Appending d_node {d_node}")
			route.append(d_node)
			#logger.debug(f"Route of length {len(route)} now is {route}")
			if len(route) > max_route_length:
				logger.debug(f"Route {route} too long (length {len(route)} > {max_route_length}), discarding")
				return None
			prev_d_node = d_node
		path_to_receiver = self.paths_to_receiver[prev_d_node]
		#logger.debug(f"path to receiver: {path_to_receiver}")
		#logger.debug(f"Appending {path_to_receiver[1:]}")
		route.extend(path_to_receiver[1:])
		if len(route) > max_route_length:
			logger.debug(f"Route {route} too long (length {len(route)} > {max_route_length}), discarding")
			return None
		assert(route[0] == self.sender and route[-1] == self.receiver)
		logger.debug(f"Returning {route}")
		return tuple(route)

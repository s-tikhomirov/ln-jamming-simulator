from queue import PriorityQueue
import networkx as nx
from random import choice
from string import digits
from random import random

from channel import ChannelDirection, ErrorType, FeeType
from params import K, M

import logging
logger = logging.getLogger(__name__)


class InFlightHtlc:
	'''
		An in-flight HTLC.
		As we don't model balances, an HTLC only contrains success-case fee.
	'''

	def __init__(self, payment_id, success_fee, desired_result):
		self.payment_id = payment_id
		self.success_fee = success_fee
		self.desired_result = desired_result

	def __repr__(self):
		s = str((self.payment_id, self.success_fee, self.desired_result))
		return s

	def __lt__(self, other):
		return self.payment_id < other.payment_id

	def __gt__(self, other):
		return other < self


class LNModel:
	'''
		A class to store the LN graph and do graph operations.
	'''

	def __init__(
		self,
		snapshot_json,
		default_num_slots,
		no_balance_failures,
		keep_receiver_upfront_fee,
		capacity_filtering_safety_margin=0.05):
		'''
			- snapshot_json
				A JSON object describing the LN graph (CLN's listchannels).

			- default_num_slots
				Default number of slots in the graph.
			- no_balance_failures
				If True, channels don't fail because of low balance.
				If False, channels fails. Probability depends on amount and capacity.

			- keep_receiver_upfront_fee
				Not nullify receiver's upfront fee revenue.
				If amount had been adjusted at Payment construction, the receiver's upfront fee is part of payment.
				Hence, technically this is not a revenue.
				However, it may be useful to leave it to check for inveriants in tests (sum of all fees == 0).

			- capacity_filtering_safety_margin
				An extra allowed capacity allowed when filtering graph for sending a given amount.

		'''
		logger.debug(f"Initializing LNModel with {default_num_slots} slots per channel direction")
		self.default_num_slots = default_num_slots
		self.get_graphs_from_json(snapshot_json)
		self.no_balance_failures = no_balance_failures
		self.keep_receiver_upfront_fee = keep_receiver_upfront_fee
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
			# TODO: generate cid randomly if not given
			src, dst, capacity, cid, is_enabled = cd["source"], cd["destination"], cd["satoshis"], cd["short_channel_id"], cd["active"]
			upfront_base_fee = cd["base_fee_millisatoshi_upfront"] / K if "base_fee_millisatoshi_upfront" in cd else None
			upfront_fee_rate = cd["fee_per_millionth_upfront"] / M if "fee_per_millionth_upfront" in cd else None
			success_base_fee = cd["base_fee_millisatoshi"] / K if "base_fee_millisatoshi" in cd else None
			success_fee_rate = cd["fee_per_millionth"] / M if "fee_per_millionth" in cd else None
			self.add_edge(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, is_enabled)
		logger.info(f"LN model created. \
			Channel graph has {self.channel_graph.number_of_nodes()} nodes and {self.channel_graph.number_of_edges()} channels. \
			Routing graph has {self.routing_graph.number_of_nodes()} nodes and {self.routing_graph.number_of_edges()} channels.")
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
		if is_enabled:
			logger.debug(f"Adding to model {src}, {dst}")
			self.add_edge_to_channel_graph(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, is_enabled, num_slots_multiplier)
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
		self.routing_graph.add_edge(src, dst, cid, capacity=capacity)

	def add_jammers_sending_channel(self, node, num_slots_multiplier, capacity=1000000):
		if (
			"JammerSender" in self.routing_graph
			and "JammerSender" in self.routing_graph.predecessors(node)):
			logger.debug(f"Already have a channel from JammerSender to {node}")
		else:
			logger.debug(f"Opening a channel from JammerSender to {node}")
			self.add_edge(
				src="JammerSender",
				dst=node,
				capacity=capacity,
				num_slots_multiplier=num_slots_multiplier)

	def add_jammers_receiving_channel(self, node, num_slots_multiplier, capacity=1000000):
		if (
			"JammerReceiver" in self.routing_graph
			and node in self.routing_graph.predecessors("JammerReceiver")):
			logger.debug(f"Already have a channel from {node} to JammerReceiver")
		else:
			logger.debug(f"Opening a channel from {node} to JammerReceiver")
			self.add_edge(
				src=node,
				dst="JammerReceiver",
				capacity=capacity,
				num_slots_multiplier=num_slots_multiplier)

	def add_jammers_channels(self, send_to_nodes, receive_from_nodes, num_slots_multiplier):
		for node in send_to_nodes:
			self.add_jammers_sending_channel(node, num_slots_multiplier=num_slots_multiplier)
		for node in receive_from_nodes:
			self.add_jammers_receiving_channel(node, num_slots_multiplier=num_slots_multiplier)

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

	def get_shortest_routes(self, sender, receiver, amount):
		route = None
		logger.debug(f"Finding route from {sender} to {receiver}")
		routing_graph = self.get_routing_graph_for_amount(
			amount=(1 + self.capacity_filtering_safety_margin) * amount)
		if sender not in routing_graph or receiver not in routing_graph:
			logger.warning(f"Can't find route from {sender} to {receiver}!")
			logger.warning(f"Sender {sender} in graph? {sender in routing_graph}")
			logger.warning(f"Sender {receiver} in graph? {receiver in routing_graph}")
			yield from ()
		if not nx.has_path(routing_graph, sender, receiver):
			logger.warning(f"No path from {sender} to {receiver}")
			yield from ()
		else:
			routes = nx.all_shortest_paths(routing_graph, sender, receiver)
			route = next(routes, None)
		while route is not None:
			yield route
			route = next(routes, None)

	def get_shortest_routes_via_nodes(self, sender, receiver, amount, must_route_via_nodes=[]):
		# Get a route from sender to (router_1 - router_2 - receiver).
		# In the jamming context, (router_1 - router_2) is the target hop.
		# We assume that the (jammer-)receiver is directly connected to router_2.
		# Although there may be multiple hops from sender to router_1.
		route = None
		is_route_via = (len(must_route_via_nodes) > 0)
		if not is_route_via:
			yield from self.get_shortest_routes(sender, receiver, amount)
		else:
			logger.debug(f"Finding route from {sender} to {receiver} via {must_route_via_nodes}")
			routing_graph = self.get_routing_graph_for_amount(
				amount=(1 + self.capacity_filtering_safety_margin) * amount)
			not_in_routing_graph = not all([n in routing_graph for n in [sender, receiver] + list(must_route_via_nodes)])
			if not_in_routing_graph:
				logger.warning(f"Can't find route from {sender} to {receiver} via {must_route_via_nodes} nodes {not_in_routing_graph} are not in the routing graph")
				yield from ()
			router_first = must_route_via_nodes[0]
			router_last = must_route_via_nodes[-1]
			if not nx.has_path(routing_graph, sender, router_first):
				logger.warning(f"No path from {sender} to {router_first}")
				yield from ()
			elif router_last not in routing_graph.predecessors(receiver):
				logger.warning(f"No (big enough) channel from {router_last} to {receiver}")
				logger.warning(f"Note: last router and receiver must be directly connected!")
				exit()
				yield from ()
			else:
				routes = nx.all_shortest_paths(routing_graph, sender, router_first)
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
		#print(u_node, d_node, channels_dict.values())

		def filter_dirs_in_hop(channels_dict, amount, direction, is_suitable):
			# Return only ch_dirs from a hop that are suitable as per is_suitable function.
			suitable_ch_dirs = [
				(cid, ch["directions"][direction]) for cid, ch in channels_dict.items()
				if is_suitable(ch["directions"][direction])]
			return suitable_ch_dirs

		def ch_dir_enabled(ch_dir):
			is_enabled = ch_dir.is_enabled if ch_dir is not None else False
			#print("is enabled?", is_enabled, ch_dir)
			return is_enabled
		
		filtered_ch_dirs = filter_dirs_in_hop(channels_dict, amount, direction, is_suitable=ch_dir_enabled)
		#print(filtered_ch_dirs)
		assert(filtered_ch_dirs)


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
		if not sorted_filtered_ch_dirs:
			print("selecting channel in hop", u_node, d_node)
			exit()
		chosen_cid, ch_dir = sorted_filtered_ch_dirs[0]
		return chosen_cid, ch_dir

	def prob_balance_failure(self, u_node, d_node, cid, amount):
		channels_dict = self.channel_graph.get_edge_data(u_node, d_node)
		return amount / channels_dict[cid]["capacity"]

	def set_fee(self, u_node, d_node, fee_type, base, rate):
		# Set a fee function of form f(a) = b + ra to the channel between u_node and d_node.
		# Note: we assume there is at most one channel between the nodes!
		logger.debug(f"Setting {fee_type.value} fee from {u_node} to {d_node} to: base {base}, rate {rate}")
		if u_node not in self.routing_graph.predecessors(d_node):
			logger.debug(f"Can't set fee: no channel from {u_node} to {d_node}")
			pass
		else:
			for ch_dir in self.get_ch_dirs((u_node, d_node)):
				if ch_dir is not None:
					ch_dir.set_fee(fee_type, base, rate)

	def set_fee_for_all(self, fee_type, base, rate):
		logger.debug(f"Setting {fee_type.value} fee for all to: base {base}, rate {rate}")
		for (u_node, d_node) in self.routing_graph.edges():
			self.set_fee(u_node, d_node, fee_type, base, rate)

	def set_upfront_fee_from_coeff_for_all(self, upfront_base_coeff, upfront_rate_coeff):
		for (u_node, d_node) in self.routing_graph.edges():
			for ch_dir in self.get_ch_dirs((u_node, d_node)):
				if ch_dir is not None:
					ch_dir.set_fee(
						FeeType.UPFRONT,
						upfront_base_coeff * ch_dir.success_base_fee,
						upfront_rate_coeff * ch_dir.success_fee_rate)

	def set_num_slots(self, u_node, d_node, num_slots):
		# Resize the slots queue to a num_slots.
		# Note: by default, this erases existing in-flight HTLCs.
		# (Which is OK as we use this to reset the graph between experiments.)
		for ch_dir in self.get_ch_dirs((u_node, d_node)):
			if ch_dir is not None:
				ch_dir.set_num_slots(num_slots)
	'''
	def get_only_ch_dir(self, u_node, d_node):
		ch_dict = self.channel_graph.get_edge_data(u_node, d_node)
		direction = (u_node < d_node)
		# assume there is only one channel in this hop
		assert(len(ch_dict.keys()) == 1)
		ch_dir = next(iter(ch_dict.values()))["directions"][direction]
		return ch_dir
	'''

	def set_deliberate_failure_behavior(self, u_node, d_node, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		for ch_dir in self.get_ch_dirs((u_node, d_node)):
			if ch_dir is not None:
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

	def finalize_in_flight_htlcs(self, now):
		'''
			Apply all in-flight htlcs with timestamp < now.
			This is done after the simulation is complete.
		'''
		# Note: we iterate through the edges of the directed routing graph,
		# but we look up HTLC data in the corresponding undirected channel graph.
		for (u_node, d_node) in self.routing_graph.edges():
			logger.debug(f"Resolving HTLCs from {u_node} to {d_node}")
			channels_dict = self.channel_graph.get_edge_data(u_node, d_node)
			direction = (u_node < d_node)
			for cid in channels_dict:
				ch_dir = channels_dict[cid]["directions"][direction]
				if ch_dir is None:
					continue
				while not ch_dir.slots.empty():
					next_htlc_time = ch_dir.slots.queue[0][0]
					if next_htlc_time > now:
						logger.debug(f"No HTLCs to resolve up to now ({now})")
						break
					resolution_time, released_htlc = ch_dir.slots.get_nowait()
					#logger.debug(f"Released HTLC {released_htlc} with resolution time {next_htlc_time}")
					self.apply_htlc(resolution_time, released_htlc, u_node, d_node, now)

	def apply_htlc(self, resolution_time, htlc, u_node, d_node, now):
		'''
			Resolve an HTLC. If (and only if) its desired result is True,
			pass success-case fee from the upstream node to the downstream node.
		'''
		assert(resolution_time <= now)  # must have been checked before popping
		if htlc.desired_result is True:
			logger.debug(f"Applying HTLC {htlc} from {u_node} to {d_node}")
			self.subtract_revenue(u_node, FeeType.SUCCESS, htlc.success_fee)
			self.add_revenue(d_node, FeeType.SUCCESS, htlc.success_fee)

	def get_ch_dirs(self, hop):
		u_node, d_node = hop
		direction = (u_node < d_node)
		ch_dict = self.channel_graph.get_edge_data(u_node, d_node)
		return [ch_dict[cid]["directions"][direction] for cid in ch_dict]

	def hop_is_jammed(self, hop, now):
		ch_dirs = self.get_ch_dirs(hop)
		return all(ch_dir.is_jammed(now) for ch_dir in ch_dirs)

	def hop_num_slots_occupied(self, hop):
		# Note: this doesn't reflect that some slots may be occupied by outdated HTLCs!
		ch_dirs = self.get_ch_dirs(hop)
		return [ch_dir.num_slots_occupied() for ch_dir in ch_dirs]

	def hop_top_timestamps(self, hop):
		ch_dirs = self.get_ch_dirs(hop)
		return [ch_dir.top_timestamp() for ch_dir in ch_dirs]

	def reset_in_flight_htlcs(self):
		logger.debug("Resetting all in-flight HTLCs")
		for u_node, d_node in self.routing_graph.edges():
			ch_dict = self.channel_graph.get_edge_data(u_node, d_node)
			direction = (u_node < d_node)
			for cid in ch_dict:
				ch_dir = ch_dict[cid]["directions"][direction]
				if ch_dir is not None:
					ch_dir.slots = PriorityQueue(maxsize=ch_dir.max_num_slots)

	def reset(self):
		self.reset_revenues_for_all()
		self.reset_in_flight_htlcs()

	def attempt_send_payment(self, payment, sender, now, attempt_id=""):
		'''
			Try sending a payment.
			The route is encoded within the payment,
			apart from the sender, which is provided as a separate argument.
		'''
		payment_attempt_id = payment.id + "-" + attempt_id
		logger.debug(f"{sender} makes payment attempt {payment_attempt_id}")
		#logger.debug(f"{payment}")
		reached_receiver, last_node_reached, first_node_not_reached, error_type = False, None, None, None
		# A temporary data structure to store HTLCs before the payment reaches the receiver
		# If the payment fails at a routing node, we don't remember in-flight HTLCs.
		import collections
		tmp_hops_to_unstored_htlcs, hops = collections.defaultdict(list), set()
		p, d_node = payment, sender
		while p is not None:
			u_node, d_node = d_node, p.downstream_node
			last_node_reached, first_node_not_reached = u_node, d_node
			hops.add((u_node, d_node))
			# Choose a channel in the required direction
			direction = (u_node < d_node)
			chosen_cid, chosen_ch_dir = self.lowest_fee_enabled_channel(u_node, d_node, p.amount, direction)
			#logger.debug(f"Routing through channel {chosen_cid} from {u_node} to {d_node}")

			# Deliberately fail the payment with some probability
			# (not used in experiments but useful for testing response to errors)
			if random() < chosen_ch_dir.deliberately_fail_prob:
				logger.debug(f"{u_node} deliberately failed payment {payment_attempt_id}")
				error_type = chosen_ch_dir.spoofing_error_type
				break

			# Model balance failures randomly, depending on the amount and channel capacity
			if not self.no_balance_failures:
				# The channel must accommodate the amount plus the upfront fee
				amount_plus_upfront_fee = p.amount + p.upfront_fee
				prob_low_balance = self.prob_balance_failure(u_node, d_node, chosen_cid, amount_plus_upfront_fee)
				if random() < prob_low_balance:
					logger.debug(f"{u_node} failed payment {payment_attempt_id}: low balance (probability was {round(prob_low_balance, 8)})")
					error_type = ErrorType.LOW_BALANCE
					break

			# Check if there is a free slot
			num_slots_needed_for_this_hop = len(tmp_hops_to_unstored_htlcs[(u_node, d_node)]) + 1
			has_free_slot, released_htlcs = chosen_ch_dir.ensure_free_slot(now, num_slots_needed=num_slots_needed_for_this_hop)
			#logger.info(f"{(u_node, d_node)} has free slot? {has_free_slot}")
			#logger.info(f"Released {len(released_htlcs)} HTLCs trying to free a slot")
			for resolution_time, released_htlc in released_htlcs:
				# Resolve the outdated HTLC we released to free a slot for the current payment
				#logger.debug(f"Released an HTLC from {u_node} to {d_node} with resolution time {resolution_time} (now is {now}): {released_htlc}")
				self.apply_htlc(resolution_time, released_htlc, u_node, d_node, now)
			if not has_free_slot:
				# All slots are busy, and there are no outdated HTLCs that could be released
				#logger.debug(f"{u_node} failed payment {payment_attempt_id}: no free slots")
				error_type = ErrorType.NO_SLOTS
				break

			# Account for upfront fees
			self.subtract_revenue(u_node, FeeType.UPFRONT, p.upfront_fee)
			# If the next payment is None, it means we've reached the receiver
			reached_receiver = p.downstream_payment is None
			if not reached_receiver or self.keep_receiver_upfront_fee:
				self.add_revenue(d_node, FeeType.UPFRONT, p.upfront_fee)

			# Construct an HTLC to be stored in a temporary dictionary until we know if receiver is reached
			in_flight_htlc = InFlightHtlc(payment_attempt_id, p.success_fee, p.desired_result)
			#logger.debug(f"Constructed HTLC: {in_flight_htlc}")
			tmp_hops_to_unstored_htlcs[(u_node, d_node)].append((chosen_cid, direction, now + p.processing_delay, in_flight_htlc))

			# Unwrap the next onion level for the next hop
			p = p.downstream_payment

		if reached_receiver:
			logger.debug(f"Payment {payment_attempt_id} has reached the receiver")
		if not reached_receiver:
			logger.debug(f"Payment {payment_attempt_id} has failed at {last_node_reached} and has NOT reached the receiver")
		#logger.debug(f"Temporarily saved HTLCs: {tmp_hops_to_unstored_htlcs}")

		# For each channel in the route, store HTLCs for the current payment
		if reached_receiver:
			last_node_reached, first_node_not_reached = d_node, None
			if payment.desired_result is False:
				error_type = ErrorType.FAILED_DELIBERATELY
			for u_node, d_node in hops:
				if (u_node, d_node) in tmp_hops_to_unstored_htlcs:
					for chosen_cid, direction, resolution_time, in_flight_htlc in tmp_hops_to_unstored_htlcs[(u_node, d_node)]:
						#logger.debug(f"Storing HTLC in channel {chosen_cid} from {u_node} to {d_node} to resolve at time {resolution_time}: {in_flight_htlc}")
						ch_dir = self.channel_graph.get_edge_data(u_node, d_node)[chosen_cid]["directions"][direction]
						# calling ensure free slot once more in case of a circular route!
						# with a circular route, we may have more than one HTLC to store
						# for a channel that has only one free slot, so we need to free up more slots, if possible
						#has_free_slot, resolution_time, released_htlc = ch_dir.ensure_free_slot(now)
						ch_dir.store_htlc(resolution_time, in_flight_htlc)

		assert(reached_receiver or error_type is not None)
		return reached_receiver, last_node_reached, first_node_not_reached, error_type

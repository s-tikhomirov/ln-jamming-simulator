import networkx as nx
from random import random
import collections

from direction import Direction
from enumtypes import ErrorType, FeeType
from channel import Channel
from hop import Hop
from htlc import InFlightHtlc
from params import K, M, ProtocolParams
from utils import generate_id

import logging
logger = logging.getLogger(__name__)


class LNModel:
	'''
		A class to store the LN graph and do graph operations.
	'''

	def __init__(
		self,
		snapshot_json,
		default_num_slots_per_channel_in_direction,
		no_balance_failures,
		capacity_filtering_safety_margin=0.05):
		'''
			- snapshot_json
				A JSON object describing the LN graph (CLN's listchannels).

			- default_num_slots_per_channel_in_direction
				Default number of slots for each channel in each direction.

			- no_balance_failures
				If True, channels don't fail because of low balance.
				If False, channels fail with probability depending on amount and capacity.

			- capacity_filtering_safety_margin
				An extra allowed capacity allowed when filtering graph for sending a given amount.
		'''
		logger.debug(f"Initializing LNModel with {default_num_slots_per_channel_in_direction} slots per channel direction")
		self.default_num_slots_per_channel_in_direction = default_num_slots_per_channel_in_direction
		self.get_graphs_from_json(snapshot_json)
		self.no_balance_failures = no_balance_failures
		# To filter graph views, add a safety margin to account for the (yet unknown) fees.
		self.capacity_filtering_safety_margin = capacity_filtering_safety_margin

	def get_graphs_from_json(self, snapshot_json):
		# Channel graph is an UNDIRECTED graph (MultiGraph).
		# Each edge corresponds to a channel. Edge id = channel id.
		# Edge attributes: capacity, directions: [ChannelInDirection0, ChannelInDirection1]
		self.channel_graph = nx.Graph()
		# Routing graph is a DIRECTED graph (MultiDiGraph) from the same JSON object.
		# Each edge corresponds to an enabled (i.e., "active") channel direction.
		# We only parse cid and capacity (it's relevant for routing).
		# All other attributes (fee functions, revenues) are stored in the undirected channel graph.
		self.routing_graph = nx.MultiDiGraph()
		logger.info(f"Creating LN model...")
		for cd in snapshot_json["channels"]:
			src, dst, capacity, cid = cd["source"], cd["destination"], cd["satoshis"], cd["short_channel_id"]
			upfront_base_fee = cd["base_fee_millisatoshi_upfront"] / K if "base_fee_millisatoshi_upfront" in cd else 0
			upfront_fee_rate = cd["fee_per_millionth_upfront"] / M if "fee_per_millionth_upfront" in cd else 0
			success_base_fee = cd["base_fee_millisatoshi"] / K if "base_fee_millisatoshi" in cd else 0
			success_fee_rate = cd["fee_per_millionth"] / M if "fee_per_millionth" in cd else 0
			if cd["active"]:
				self.add_edge(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate)
		logger.info(f"LN model created.")
		logger.info(f"Channel graph has {self.channel_graph.number_of_nodes()} nodes and {self.channel_graph.number_of_edges()} channels.")
		logger.info(f"Routing graph has {self.routing_graph.number_of_nodes()} nodes and {self.routing_graph.number_of_edges()} channels.")
		self.reset_all_revenues()

	def add_edge(self, src, dst, capacity, cid=None, upfront_base_fee=0, upfront_fee_rate=0, success_base_fee=0, success_fee_rate=0, num_slots=None):
		if cid is None:
			cid = src[:1] + dst[:1] + "x" + generate_id(length=4)
		if num_slots is None:
			num_slots = self.default_num_slots_per_channel_in_direction
		self.add_edge_to_channel_graph(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, num_slots)
		self.add_edge_to_routing_graph(src, dst, capacity, cid)

	def add_edge_to_channel_graph(self, src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, num_slots):
		for node in (src, dst):
			if node not in self.channel_graph:
				self.channel_graph.add_node(node)
				self.set_revenue(node, upfront_revenue=0, success_revenue=0)
		if not self.channel_graph.has_edge(src, dst):
			hop = Hop()
			self.channel_graph.add_edge(src, dst, hop=hop)
		hop = self.get_hop(src, dst)
		if not hop.has_channel(cid):
			ch = Channel(capacity, cid)
			hop.add_channel(ch)
		else:
			ch = hop.get_channel(cid)
		direction = Direction(src, dst)
		ch.enable_direction_with_num_slots(direction, num_slots)
		ch.set_fee_in_direction(direction, FeeType.UPFRONT, upfront_base_fee, upfront_fee_rate)
		ch.set_fee_in_direction(direction, FeeType.SUCCESS, success_base_fee, success_fee_rate)

	def add_edge_to_routing_graph(self, src, dst, capacity, cid):
		# We need cid here as well as in the channel graph.
		# We look for routes in the (filtered) routing graph,
		# and then pull hop info from the channel graph based on the chosen cid.
		self.routing_graph.add_edge(src, dst, cid, capacity=capacity)

	def add_jammers_channels(self, send_to_nodes=[], receive_from_nodes=[], num_slots=ProtocolParams["NUM_SLOTS"], capacity=1000000):
		assert send_to_nodes or receive_from_nodes
		for node in send_to_nodes:
			if not ("JammerSender" in self.routing_graph and "JammerSender" in self.routing_graph.predecessors(node)):
				logger.debug(f"Opening a channel from JammerSender to {node}")
				self.add_edge(src="JammerSender", dst=node, capacity=capacity, num_slots=num_slots)
		for node in receive_from_nodes:
			if (not ("JammerReceiver" in self.routing_graph and node in self.routing_graph.predecessors("JammerReceiver"))):
				logger.debug(f"Opening a channel from {node} to JammerReceiver")
				self.add_edge(src=node, dst="JammerReceiver", capacity=capacity, num_slots=num_slots)

	def add_revenue(self, node, fee_type, amount):
		assert node in self.channel_graph
		self.channel_graph.nodes[node][fee_type.value] += amount

	def subtract_revenue(self, node, fee_type, amount):
		self.add_revenue(node, fee_type, -amount)

	def shift_revenue(self, from_node, to_node, fee_type, amount):
		logger.debug(f"{from_node} pays {to_node} {amount} in {fee_type.value} fee")
		self.subtract_revenue(from_node, fee_type, amount)
		self.add_revenue(to_node, fee_type, amount)

	def get_revenue(self, node, fee_type):
		assert node in self.channel_graph
		return self.channel_graph.nodes[node][fee_type.value]

	def get_routing_graph_for_amount(self, amount):
		# Return a graph view that only includes edges with capacity >= amount with safety margin
		amount_with_safety_margin = (1 + self.capacity_filtering_safety_margin) * amount

		def filter_edges(n1, n2, cid):
			return self.routing_graph[n1][n2][cid]["capacity"] >= amount_with_safety_margin
		logger.debug(f"Filtering out edges with capacity < {amount_with_safety_margin}")
		return nx.subgraph_view(self.routing_graph, lambda _: True, filter_edges)

	def get_shortest_routes(self, sender, receiver, amount):
		route = None
		logger.debug(f"Finding route from {sender} to {receiver}")
		routing_graph = self.get_routing_graph_for_amount(amount)
		if sender not in routing_graph or receiver not in routing_graph:
			logger.warning(f"Can't find route from {sender} to {receiver}!")
			logger.warning(f"Sender {sender} in graph? {sender in routing_graph}")
			logger.warning(f"Sender {receiver} in graph? {receiver in routing_graph}")
			yield from ()
		elif not nx.has_path(routing_graph, sender, receiver):
			logger.warning(f"No path from {sender} to {receiver}")
			yield from ()
		else:
			routes = nx.all_shortest_paths(routing_graph, sender, receiver)
			route = next(routes, None)
			while route is not None:
				yield route
				route = next(routes, None)

	def get_hop(self, u_node, d_node):
		assert u_node != d_node
		assert self.channel_graph.has_edge(u_node, d_node)
		return self.channel_graph.get_edge_data(u_node, d_node)["hop"]

	def reset_all_slots(self, num_slots=None):
		logger.debug("Resetting slots in all channels")
		for node_1, node_2 in self.channel_graph.edges():
			for ch in self.get_hop(node_1, node_2).get_all_channels():
				for direction in (Direction.Alph, Direction.NonAlph):
					logger.debug(f"Resetting channel {ch.get_cid()} ({node_1} - {node_2}) in {direction} with num slots = {num_slots}")
					ch.reset_slots_in_direction(direction, num_slots)

	def set_revenue(self, node, upfront_revenue, success_revenue):
		assert node in self.channel_graph
		self.channel_graph.nodes[node][FeeType.UPFRONT.value] = upfront_revenue
		self.channel_graph.nodes[node][FeeType.SUCCESS.value] = success_revenue

	def reset_all_revenues(self):
		logger.debug("Resetting all revenues")
		for node in self.channel_graph.nodes:
			self.set_revenue(node, upfront_revenue=0, success_revenue=0)

	def set_fee_for_all(self, fee_type, base, rate):
		logger.debug(f"Setting {fee_type.value} fee for all to: base {base}, rate {rate}")
		for node_1, node_2 in self.channel_graph.edges():
			for ch in self.get_hop(node_1, node_2).get_all_channels():
				for direction in (Direction.Alph, Direction.NonAlph):
					if ch.is_enabled_in_direction(direction):
						ch.in_direction(direction).set_fee(fee_type, base, rate)

	def set_upfront_fee_from_coeff_for_all(self, upfront_base_coeff, upfront_rate_coeff):
		logger.debug(f"Setting upfront fee for all as share of success fee with: base coeff {upfront_base_coeff}, rate coeff {upfront_rate_coeff}")
		for node_1, node_2 in self.channel_graph.edges():
			for ch in self.get_hop(node_1, node_2).get_all_channels():
				for direction in (Direction.Alph, Direction.NonAlph):
					if ch.is_enabled_in_direction(direction):
						ch_in_dir = ch.in_direction(direction)
						ch_in_dir.set_fee(
							FeeType.UPFRONT,
							upfront_base_coeff * ch_in_dir.success_base_fee,
							upfront_rate_coeff * ch_in_dir.success_fee_rate)

	def finalize_in_flight_htlcs(self, cutoff_time):
		'''
			Apply all in-flight htlcs with timestamp < now.
			This is done after the simulation is complete.
		'''
		# Note: (node_1, node_2) are not ordered!
		for node_1, node_2 in self.channel_graph.edges():
			for ch in self.get_hop(node_1, node_2).get_all_channels():
				for from_node, to_node in ((node_1, node_2), (node_2, node_1)):
					#logger.debug(f"Resolving HTLCs from {from_node} and {to_node}")
					direction = Direction(from_node, to_node)
					if ch.is_enabled_in_direction(direction):
						ch_in_dir = ch.in_direction(direction)
						while not ch_in_dir.all_slots_free():
							if ch_in_dir.get_top_timestamp() > cutoff_time:
								break
							resolution_time, htlc = ch_in_dir.pop_htlc()
							#logger.debug(f"Released HTLC {htlc} with resolution time {next_htlc_time}")
							if htlc.desired_result is True:
								self.shift_revenue(from_node, to_node, FeeType.SUCCESS, htlc.success_fee)
						#logger.debug(f"No more HTLCs to resolve up to time ({cutoff_time})")

	def attempt_send_payment(self, payment, sender, now, attempt_num=0):
		'''
			Try sending a payment.
			The route is encoded within the payment,
			apart from the sender, which is provided as a separate argument.
		'''
		payment_attempt_id = payment.id + "-" + str(attempt_num)
		logger.debug(f"{sender} makes payment attempt {payment_attempt_id}")
		last_node_reached, first_node_not_reached = sender, payment.downstream_node
		# A temporary data structure to store HTLCs before we know if the payment has reached the receiver.
		# If not, we discard in-flight HTLCs along the route.
		unstored_htlcs_for_hop = collections.defaultdict(list)
		p, d_node = payment, sender
		reached_receiver, error_type = False, None
		while not reached_receiver:
			u_node, d_node = d_node, p.downstream_node
			last_node_reached, first_node_not_reached = u_node, d_node
			is_last_hop = p.downstream_payment is None

			logger.debug(f"Trying to route via cheapest channel from {u_node} to {d_node}")
			hop = self.get_hop(u_node, d_node)
			direction = Direction(u_node, d_node)
			has_free_slot = hop.really_can_forward_in_direction_at_time(direction, now, p.get_amount())
			if has_free_slot:
				# A channel may be able to forward with one free slot,
				# but we may need multiple slots to store HTLCs already created for this hop in this (circular) payment.
				# We now try to ensure as many slots as we really need!
				# We may pop some (outdated) HTLCs while doing that, and apply them.
				# TODO: what happens after the cheapest channel is jammed?
				chosen_ch = hop.get_cheapest_channel_really_can_forward(direction, now, p.get_amount())
				chosen_ch_in_dir = chosen_ch.in_direction(direction)
				chosen_cid = chosen_ch.get_cid()
				logger.debug(f"Chosen channel {chosen_cid}")
				# Construct an HTLC to keep in a temporary dictionary until we know if we reach the receiver
				in_flight_htlc = InFlightHtlc(payment_attempt_id, p.success_fee, p.desired_result)
				unstored_htlcs_for_hop[(u_node, d_node)].append((chosen_ch.get_cid(), direction, now + p.processing_delay, in_flight_htlc))
				num_slots_needed_for_this_hop = len(unstored_htlcs_for_hop[(u_node, d_node)])
				has_free_slot, popped_htlcs = chosen_ch_in_dir.ensure_free_slots(now, num_slots_needed=num_slots_needed_for_this_hop)
				for resolution_time, popped_htlc in popped_htlcs:
					assert resolution_time <= now
					logger.debug(f"Popped an HTLC in {u_node}-{d_node}: resolution time {resolution_time} (now is {now}): {popped_htlc}")
					if popped_htlc.desired_result is True:
						self.shift_revenue(u_node, d_node, FeeType.SUCCESS, popped_htlc.success_fee)
			if not has_free_slot:
				logger.debug(f"No channel in {u_node}-{d_node} can forward payment {p.id}!")
				error_type = ErrorType.NO_SLOTS
				break

			# Deliberately fail the payment with some probability
			if random() < chosen_ch_in_dir.deliberately_fail_prob:
				logger.debug(f"{u_node} deliberately failed payment {payment_attempt_id}")
				error_type = chosen_ch_in_dir.spoofing_error_type
				break

			# Fail the payment randomly, depending on the amount and channel capacity
			if not self.no_balance_failures:
				# The channel must accommodate the amount plus the upfront fee
				prob_low_balance = p.get_amount_plus_upfront_fee() / chosen_ch.get_capacity()
				assert 0 < prob_low_balance <= 1
				if random() < prob_low_balance:
					logger.debug(f"{u_node} failed payment {payment_attempt_id}: low balance (probability was {round(prob_low_balance, 8)})")
					error_type = ErrorType.LOW_BALANCE
					break

			# Fail if the payment doesn't pay sufficient fees
			zero_success_fee = is_last_hop
			for fee_type in (FeeType.UPFRONT, FeeType.SUCCESS):
				fee_required = chosen_ch_in_dir.requires_fee(fee_type, p, zero_success_fee)
				fee_paid = p.pays_fee(fee_type)
				logger.debug(f"{fee_type} fee at {chosen_cid} required / offered: {fee_required} / {fee_paid}")
			if not chosen_ch_in_dir.enough_total_fee(p, zero_success_fee):
				error_type = ErrorType.LOW_FEE
				break

			# Account for upfront fees
			self.shift_revenue(u_node, d_node, FeeType.UPFRONT, p.upfront_fee)

			# Unwrap the payment for the next hop
			p = p.downstream_payment
			reached_receiver = p is None

		# For each channel in the route, store HTLCs for the current payment
		if reached_receiver:
			logger.debug(f"Payment {payment_attempt_id} has reached the receiver")
			#logger.debug(f"Temporarily saved HTLCs: {unstored_htlcs_for_hop}")
			last_node_reached, first_node_not_reached = d_node, None
			if payment.desired_result is False:
				error_type = ErrorType.FAILED_DELIBERATELY
			#logger.debug(f"Temporarily saved HTLCs: {unstored_htlcs_for_hop}")
			for (u_node, d_node) in unstored_htlcs_for_hop:
				for chosen_cid, direction, resolution_time, in_flight_htlc in unstored_htlcs_for_hop[(u_node, d_node)]:
					logger.debug(f"Storing HTLC in channel {chosen_cid} from {u_node} to {d_node} to resolve at time {resolution_time}: {in_flight_htlc}")
					ch_in_dir = self.get_hop(u_node, d_node).get_channel(chosen_cid).in_direction(direction)
					ch_in_dir.push_htlc(resolution_time, in_flight_htlc)
		else:
			logger.debug(f"Payment {payment_attempt_id} has failed at {last_node_reached} and has NOT reached the receiver")

		assert reached_receiver or error_type is not None
		return reached_receiver, last_node_reached, first_node_not_reached, error_type

	def report_revenues(self):  # pragma: no cover
		print("\n\n*** Revenues ***")
		for node in self.channel_graph.nodes:
			success_revenue = self.get_revenue(node, FeeType.SUCCESS)
			upfront_revenue = self.get_revenue(node, FeeType.UPFRONT)
			print("\n", node)
			print("Upfront:", upfront_revenue)
			print("Success:", success_revenue)
			print("Total:", upfront_revenue + success_revenue)

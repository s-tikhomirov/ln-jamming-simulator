import networkx as nx
from random import random
import collections

from direction import Direction
from channelindirection import ChannelInDirection
from enumtypes import ErrorType, FeeType
from channel import Channel
from hop import Hop
from htlc import InFlightHtlc
from params import K, M
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
		default_num_slots,
		no_balance_failures,
		keep_receiver_upfront_fee=True,
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
		num_slots=None):
		if cid is None:
			cid = src[:1] + dst[:1] + "x" + generate_id(length=4)
		if num_slots is None:
			num_slots = self.default_num_slots
		self.add_edge_to_channel_graph(src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, num_slots)
		self.add_edge_to_routing_graph(src, dst, capacity, cid)

	def add_edge_to_channel_graph(self, src, dst, capacity, cid, upfront_base_fee, upfront_fee_rate, success_base_fee, success_fee_rate, num_slots):
		chdir = ChannelInDirection(
			num_slots=num_slots,
			upfront_base_fee=upfront_base_fee,
			upfront_fee_rate=upfront_fee_rate,
			success_base_fee=success_base_fee,
			success_fee_rate=success_fee_rate
		)
		for node in (src, dst):
			if node not in self.channel_graph:
				self.channel_graph.add_node(node)
				self.reset_revenue(node)
		if not self.channel_graph.has_edge(src, dst):
			hop = Hop()
			self.channel_graph.add_edge(src, dst, hop=hop)
		hop = self.channel_graph.get_edge_data(src, dst)["hop"]
		if not hop.has_cid(cid):
			ch = Channel(capacity)
			hop.add_channel(ch, cid)
		else:
			ch = hop.get_channel(cid)
		ch.add_chdir(chdir, Direction(src, dst))

	def add_edge_to_routing_graph(self, src, dst, capacity, cid):
		# TODO: do we need cid here?
		self.routing_graph.add_edge(src, dst, cid, capacity=capacity)

	def add_jammers_sending_channel(self, node, num_slots, capacity=1000000):
		if not ("JammerSender" in self.routing_graph and "JammerSender" in self.routing_graph.predecessors(node)):
			logger.debug(f"Opening a channel from JammerSender to {node}")
			self.add_edge(src="JammerSender", dst=node, capacity=capacity, num_slots=num_slots)

	def add_jammers_receiving_channel(self, node, num_slots, capacity=1000000):
		if (not ("JammerReceiver" in self.routing_graph and node in self.routing_graph.predecessors("JammerReceiver"))):
			logger.debug(f"Opening a channel from {node} to JammerReceiver")
			self.add_edge(src=node, dst="JammerReceiver", capacity=capacity, num_slots=num_slots)

	def add_jammers_channels(self, send_to_nodes, receive_from_nodes, num_slots):
		for node in send_to_nodes:
			self.add_jammers_sending_channel(node, num_slots=num_slots)
		for node in receive_from_nodes:
			self.add_jammers_receiving_channel(node, num_slots=num_slots)

	def add_revenue(self, node, fee_type, amount):
		self.channel_graph.nodes[node][fee_type.value] += amount

	def subtract_revenue(self, node, fee_type, amount):
		self.add_revenue(node, fee_type, -amount)

	def get_revenue(self, node, fee_type):
		return self.channel_graph.nodes[node][fee_type.value]

	def get_hop(self, u_node, d_node):
		assert(u_node != d_node)
		if not self.channel_graph.has_edge(u_node, d_node):
			logger.debug(f"No edge in channel graph between {u_node} {d_node}")
		assert(self.channel_graph.has_edge(u_node, d_node))
		return self.channel_graph.get_edge_data(u_node, d_node)["hop"]

	def get_routing_graph_edge_data(self, u_node, d_node):
		return self.routing_graph.get_edge_data(u_node, d_node)

	def get_cids_can_forward_by_fee(self, u_node, d_node, amount):
		hop = self.get_hop(u_node, d_node)
		return hop.get_cids_can_forward_by_fee(amount, Direction(u_node, d_node))

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
		elif not nx.has_path(routing_graph, sender, receiver):
			logger.warning(f"No path from {sender} to {receiver}")
			yield from ()
		else:
			routes = nx.all_shortest_paths(routing_graph, sender, receiver)
			route = next(routes, None)
			while route is not None:
				yield route
				route = next(routes, None)

	def get_cheapest_cid_in_hop(self, u_node, d_node, amount):
		# TODO: think about the logic of jamming vs choosing cheapest channel
		# what happens after the cheapest channel is jammed?
		logger.debug(f"Choosing cheapest cid in hop from {u_node} to {d_node}")
		hop = self.get_hop(u_node, d_node)
		#logger.debug(f"Hop: {hop}")
		return hop.get_cheapest_cid(amount, Direction(u_node, d_node))

	def get_prob_balance_failure(self, u_node, d_node, cid, amount):
		channels_dict = self.get_routing_graph_edge_data(u_node, d_node)
		return amount / channels_dict[cid]["capacity"]

	def set_fee_for_all(self, fee_type, base, rate):
		logger.debug(f"Setting {fee_type.value} fee for all to: base {base}, rate {rate}")
		for (u_node, d_node) in self.routing_graph.edges():
			assert(u_node in self.routing_graph.predecessors(d_node))
			logger.debug(f"Setting {fee_type.value} fee from {u_node} to {d_node} to: base {base}, rate {rate}")
			for ch_dir in self.get_ch_dirs((u_node, d_node)):
				if ch_dir is not None:
					ch_dir.set_fee(fee_type, base, rate)

	def set_upfront_fee_from_coeff_for_all(self, upfront_base_coeff, upfront_rate_coeff):
		for (u_node, d_node) in self.routing_graph.edges():
			for ch_dir in self.get_ch_dirs((u_node, d_node)):
				if ch_dir is not None:
					ch_dir.set_fee(
						FeeType.UPFRONT,
						upfront_base_coeff * ch_dir.success_base_fee,
						upfront_rate_coeff * ch_dir.success_fee_rate)

	def reset_with_num_slots(self, u_node, d_node, num_slots):
		# Resize the slots queue to a num_slots.
		# Note: this erases existing in-flight HTLCs.
		# (Which is OK as we use this to reset the graph between experiments.)
		logger.debug(f"Resetting {u_node}-{d_node} with num slots = {num_slots}")
		for ch_dir in self.get_ch_dirs((u_node, d_node)):
			if ch_dir is not None:
				ch_dir.reset_with_num_slots(num_slots)

	def finalize_in_flight_htlcs(self, now):
		'''
			Apply all in-flight htlcs with timestamp < now.
			This is done after the simulation is complete.
		'''
		# Note: (node_1, node_2) are not ordered.
		# We iterate through all edges in the CHANNEL graph and release HTLC for both directions, if present.
		# The direction to resolve the HTLC in is taken from the HTLC itself.
		# The order of (node_1, node_2) plays no role here!
		for (node_1, node_2) in self.channel_graph.edges():
			#logger.debug(f"Resolving HTLCs between {node_1} and {node_2}")
			hop = self.get_hop(node_1, node_2)
			for ch in hop.get_channels():
				for (u_node, d_node) in ((node_1, node_2), (node_2, node_1)):
					ch_dir = ch.directions[Direction(u_node, d_node)]
					if ch_dir is not None:
						while not ch_dir.is_empty():
							next_htlc_time = ch_dir.get_top_timestamp()
							if next_htlc_time > now:
								break
							resolution_time, released_htlc = ch_dir.get_htlc()
							#logger.debug(f"Released HTLC {released_htlc} with resolution time {next_htlc_time}")
							self.apply_htlc(resolution_time, released_htlc, u_node, d_node, now)
						#logger.debug(f"No more HTLCs to resolve up to now ({now})")

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
		hop_data = self.get_hop(u_node, d_node)
		return [hop_data.get_channel(cid).directions[Direction(u_node, d_node)] for cid in hop_data.channels]

	def hop_is_jammed(self, hop, now):
		ch_dirs = self.get_ch_dirs(hop)
		return all(ch_dir.is_jammed(now) if ch_dir is not None else True for ch_dir in ch_dirs)

	def reset_in_flight_htlcs(self):
		logger.debug("Resetting all in-flight HTLCs")
		# NB: this was routing_graph before!
		for u_node, d_node in self.channel_graph.edges():
			hop = self.get_hop(u_node, d_node)
			for cid in hop.get_cids():
				ch = hop.get_channel(cid)
				ch.reset_in_flight_htlcs()

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
		reached_receiver, error_type = False, None
		last_node_reached, first_node_not_reached = sender, payment.downstream_node
		# A temporary data structure to store HTLCs before the payment reaches the receiver
		# If the payment fails at a routing node, we don't remember in-flight HTLCs.
		tmp_hops_to_unstored_htlcs, hops = collections.defaultdict(list), set()
		p, d_node = payment, sender
		while p is not None:
			u_node, d_node = d_node, p.downstream_node
			last_node_reached, first_node_not_reached = u_node, d_node
			hops.add((u_node, d_node))
			#chosen_cid, chosen_ch_dir = self.lowest_fee_enabled_channel(u_node, d_node, p.amount)
			#logger.debug(f"Routing through channel {chosen_cid} from {u_node} to {d_node}")
			chosen_cid = self.get_cheapest_cid_in_hop(u_node, d_node, p.amount)
			chosen_ch_dir = self.get_hop(u_node, d_node).get_channel(chosen_cid).directions[Direction(u_node, d_node)]

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
				prob_low_balance = self.get_prob_balance_failure(u_node, d_node, chosen_cid, amount_plus_upfront_fee)
				if random() < prob_low_balance:
					logger.debug(f"{u_node} failed payment {payment_attempt_id}: low balance (probability was {round(prob_low_balance, 8)})")
					error_type = ErrorType.LOW_BALANCE
					break

			# Check if there is a free slot
			num_slots_needed_for_this_hop = len(tmp_hops_to_unstored_htlcs[(u_node, d_node)]) + 1
			has_free_slot, released_htlcs = chosen_ch_dir.ensure_free_slot(now, num_slots_needed=num_slots_needed_for_this_hop)
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
			tmp_hops_to_unstored_htlcs[(u_node, d_node)].append((chosen_cid, Direction(u_node, d_node), now + p.processing_delay, in_flight_htlc))

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
			logger.debug(f"temporarily saved HTLCs: {tmp_hops_to_unstored_htlcs}")
			for u_node, d_node in hops:
				if (u_node, d_node) in tmp_hops_to_unstored_htlcs:
					for chosen_cid, direction, resolution_time, in_flight_htlc in tmp_hops_to_unstored_htlcs[(u_node, d_node)]:
						logger.debug(f"Storing HTLC in channel {chosen_cid} from {u_node} to {d_node} to resolve at time {resolution_time}: {in_flight_htlc}")
						ch_dir = self.get_hop(u_node, d_node).get_channel(chosen_cid).directions[direction]
						ch_dir.store_htlc(resolution_time, in_flight_htlc)

		assert(reached_receiver or error_type is not None)
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

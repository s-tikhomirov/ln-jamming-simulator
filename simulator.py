from payment import Payment
from channel_selection import lowest_fee_enabled_channel
from lnmodel import RevenueType
from channel import dir0, dir1, ErrorType
from params import ProtocolParams

from random import random


def body_for_amount(target_amount, upfront_fee_function, precision=1, max_steps=50):
	'''
		Given target_amount and fee function, find amount such that:
		amount + fee(amount) ~ target_amount
	'''
	min_body, max_body, num_step = 0, target_amount, 0
	while True:
		num_step += 1
		body = round((min_body + max_body) / 2)
		fee = upfront_fee_function(body)
		amount = body + fee
		if abs(target_amount - amount) < precision or num_step > max_steps:
			break
		if amount < target_amount:
			min_body = body
		else:
			max_body = body
	return body


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


class Simulator:
	'''
		The Simulator class executes a Schedule of Events.
		For each Event, it builds a route, creates a Payment, and routes it.
		The resulting changes in revenues are written into the LNModel.
	'''

	def __init__(self, ln_model):
		self.ln_model = ln_model

	def execute_schedule(
		self,
		schedule,
		simulation_cutoff,
		target_node_pair=None,
		jam_with_insertion=False,
		enforce_dust_limit=True,
		no_balance_failures=False,
		subtract_last_hop_upfront_fee_for_honest_payments=True,
		keep_receiver_upfront_fee=False,
		max_num_attempts_per_route_honest=1,
		max_num_attempts_per_route_jamming=1):
		'''
			Parameters:
			- schedule
				A Schedule to execute.

			- simulation_cutoff
				When to end the simulation.
				Simulation end is different from the timestamp of the last event (which is earlier).
				It determines which HTLCs to finalize after all Events are processed.

			- target_node_pair
				Build routes such that they pass through this pair of nodes, in this order (used in jamming).

			- jam_with_insertion
				Insert new jam Events into Schedule while processing existing Events, depending on jam results.

			- enforce_dust_limit
				Not allow creating Payments with amount smaller than ProtocolParams["DUST_LIMIT"].

			- no_balance_failures
				Disable balance-based failures. Otherwise, fail with probability (amount / capacity).

			- subtract_last_hop_upfront_fee_for_honest_payments
				Apply body_for_amount at Payment construction for honest payment.
				Jams are always constructed without such adjustment to stay above the dust limit at all hops.

			- keep_receiver_upfront_fee
				Not nullify receiver's upfront fee revenue.
				If amount had been adjusted at Payment construction, the receiver's upfront fee is part of payment.
				Hence, technically this is not a revenue.
				However, it may be useful to leave it to check for inveriants in tests (sum of all fees == 0).

			- max_num_attempts_per_route_honest
				The maximum number of attempts to send an honest payment.

			- max_num_attempts_per_route_jamming
				The maximul number of attempts to send a jam (which is probably higher than that for honest payments).
		'''
		now, num_sent, num_failed, num_reached_receiver = -1, 0, 0, 0
		# we make the first attempt unconditionally
		num_jam_attempts_this_batch = 1
		while not schedule.schedule.empty():
			new_time, event = schedule.get_event()
			# we count every attempt into "num_sent"
			num_attempts = 0
			if new_time > now:
				#print("Current time:", new_time)
				pass
			now = new_time
			if now > simulation_cutoff:
				#print("Reached simulation end time.", now, simulation_cutoff)
				break
			#print("Got event:", event)
			is_jam = event.desired_result is False
			if target_node_pair is not None:
				router_1, router_2 = target_node_pair
				routes = self.ln_model.get_routes_via_hop(event.sender, router_1, router_2, event.receiver, event.amount)
			else:
				# it's OK to use un-adjusted amount here: we allow for a safety margin for fees
				routes = self.ln_model.get_routes(event.sender, event.receiver, event.amount)
			try:
				route = next(routes)
				#print("Found route:", route)
			except StopIteration:
				#print("No route, skipping event")
				continue
			if is_jam or not subtract_last_hop_upfront_fee_for_honest_payments:
				receiver_amount = event.amount
			else:
				#print("Subtracting last-hop upfront fee from amount")
				receiver_amount = self.get_adjusted_amount(event.amount, route)
			#print("Receiver will get:", event.amount, "/ in payment body:", receiver_amount)
			p = self.create_payment(route, receiver_amount, event.processing_delay, event.desired_result, enforce_dust_limit)
			#print("Constructed payment:", p)
			while num_attempts < (1 if is_jam else max_num_attempts_per_route_honest):
				num_attempts += 1
				reached_receiver, erring_node, error_type = self.attempt_send_payment(
					p, event.sender, now, no_balance_failures, keep_receiver_upfront_fee)
				if error_type is not None:
					num_failed += 1
				if reached_receiver:
					num_reached_receiver += 1
					break
			num_sent += num_attempts
			if is_jam and jam_with_insertion:
				if reached_receiver:
					#print("Jam reached receiver")
					#print("Putting this jam into schedule again:", now, event)
					schedule.put_event(now, event)
				else:
					#print("Jam failed at", erring_node, error_type)
					next_batch_time = now + event.processing_delay
					if error_type in (ErrorType.LOW_BALANCE, ErrorType.FAILED_DELIBERATELY):
						if num_jam_attempts_this_batch < max_num_attempts_per_route_jamming:
							# we didn't jam because of error, continue this batch
							schedule.put_event(now, event)
							num_jam_attempts_this_batch += 1
						else:
							# we've tried many times, haven't fully jammed, moving on to the next batch
							#print("Coundn't fully jam target at time", now)
							schedule.put_event(next_batch_time, event)
							num_jam_attempts_this_batch = 1
					elif error_type == ErrorType.NO_SLOTS:
						sender, pre_receiver = route[0], route[-2]
						if erring_node in (sender, pre_receiver):
							#print("WARNING: Jammer's slots depleted. Allocate more slots to jammer's channels!")
							pass
						else:
							#print("Fully jammed at time", now, ". Waiting until the next batch.")
							pass
						num_jam_attempts_this_batch = 1
						schedule.put_event(next_batch_time, event)
		#print("Schedule executed.")
		#print("Handled events:", num_sent)
		now = simulation_cutoff
		#print("Now is simulation end time:", now)
		# resolve all in-flight htlcs
		#print("Finalizing in-flight HTLCs...")
		self.finalize_in_flight_htlcs(now)
		#print("Simulation complete.")
		return num_sent, num_failed, num_reached_receiver

	def attempt_send_payment(self, payment, sender, now, no_balance_failures, keep_receiver_upfront_fee):
		'''
			Try sending a payment.
			The route is encoded within the payment,
			apart from the sender, which is provided as a separate argument.
			Make just one attempt; re-tries are implemented at the caller.
		'''
		#print("SENDING PAYMENT", payment.id)
		erring_node, error_type, reached_receiver = None, None, False
		# A temporary data structure to store HTLCs before the payment reaches the receiver
		# If the payment fails at a routing node, we don't remember in-flight HTLCs.
		tmp_cid_to_htlcs, hops = dict(), []
		#print("Attempt", num_attempts, "of", max_num_attempts_per_route_honest)
		p, d_node = payment, sender
		while p is not None:
			u_node, d_node = d_node, p.downstream_node
			hops.append((u_node, d_node))
			# Choose a channel in the required direction
			channels_dict = self.ln_model.channel_graph.get_edge_data(u_node, d_node)
			direction = (u_node < d_node)
			chosen_cid, chosen_ch_dir = lowest_fee_enabled_channel(channels_dict, p.amount, direction)
			#print("Chose channel to forward:", chosen_cid)
			#print(chosen_ch_dir)

			# Deliberately fail the payment with some probability
			# (not used in experiments but useful for testing response to errors)
			if random() < chosen_ch_dir.deliberately_fail_prob:
				#print("Node", u_node, "deliberately fails payment")
				erring_node, error_type = u_node, chosen_ch_dir.spoofing_error_type
				break

			# Model balance failures randomly, depending on the amount and channel capacity
			if not no_balance_failures:
				# The channel must accommodate the amount plus the upfront fee
				amount_plus_upfront_fee = p.amount + p.upfront_fee
				prob_low_balance = amount_plus_upfront_fee / channels_dict[chosen_cid]["capacity"]
				#print("Probability of balance failure:", prob_low_balance)
				if random() < prob_low_balance:
					#print("Low balance:", u_node, "fails payment")
					erring_node, error_type = u_node, ErrorType.LOW_BALANCE
					break

			# Check if there is a free slot
			has_free_slot, resolution_time, released_htlc = chosen_ch_dir.ensure_free_slot(now)
			if released_htlc is not None:
				# Resolve the outdated HTLC we released to free a slot for the current payment
				#print("Popped htlc from", u_node, d_node, ":", resolution_time, released_htlc)
				self.apply_htlc(resolution_time, released_htlc, u_node, d_node, now)
			if not has_free_slot:
				# All slots are busy, and there are no outdated HTLCs that could be released
				#print("No free slots:", u_node, "fails payment")
				erring_node, error_type = u_node, ErrorType.NO_SLOTS
				break

			# Account for upfront fees
			self.ln_model.subtract_revenue(u_node, RevenueType.UPFRONT, p.upfront_fee)
			# If the next payment is None, it means we've reached the receiver
			reached_receiver = p.downstream_payment is None
			if not reached_receiver or keep_receiver_upfront_fee:
				self.ln_model.add_revenue(d_node, RevenueType.UPFRONT, p.upfront_fee)

			# Construct an HTLC to be stored in a temporary dictionary until we know if receiver is reached
			in_flight_htlc = InFlightHtlc(p.id, p.success_fee, p.desired_result)
			#print("Constructed htlc:", in_flight_htlc)
			tmp_cid_to_htlcs[(u_node, d_node)] = chosen_cid, direction, now + p.processing_delay, in_flight_htlc

			# Unwrap the next onion level for the next hop
			p = p.downstream_payment

		#print("Reached receiver:", reached_receiver)
		#print("erring_node:", erring_node)
		#print("Temporarily saved htlcs:", tmp_cid_to_htlcs)

		# For each channel in the route, store HTLCs for the current payment
		if reached_receiver:
			if payment.desired_result is False:
				error_type = ErrorType.FAILED_DELIBERATELY
			for u_node, d_node in hops:
				if (u_node, d_node) in tmp_cid_to_htlcs:
					chosen_cid, direction, resolution_time, in_flight_htlc = tmp_cid_to_htlcs[(u_node, d_node)]
					#print("Storing htlc for", chosen_cid, "to resolve at time", resolution_time, ":", in_flight_htlc)
					ch_dir = self.ln_model.channel_graph.get_edge_data(u_node, d_node)[chosen_cid]["directions"][direction]
					ch_dir.store_htlc(resolution_time, in_flight_htlc)

		assert(reached_receiver or error_type is not None)
		return reached_receiver, erring_node, error_type

	def finalize_in_flight_htlcs(self, now):
		'''
			Apply all in-flight htlcs with timestamp < now.
			This is done after the simulation is complete.
		'''
		for (node_a, node_b) in self.ln_model.channel_graph.edges():
			channels_dict = self.ln_model.channel_graph.get_edge_data(node_a, node_b)
			for cid in channels_dict:
				for direction in [dir0, dir1]:
					ch_dir = channels_dict[cid]["directions"][direction]
					if ch_dir is None:
						continue
					while not ch_dir.slots.empty():
						next_htlc_time = ch_dir.slots.queue[0][0]
						#print("Next HTLC resolution time is:", next_htlc_time)
						if next_htlc_time > now:
							#print("No HTLCs to resolve before current time.")
							break
						resolution_time, released_htlc = ch_dir.slots.get_nowait()
						#print(resolution_time, released_htlc)
						self.apply_htlc(resolution_time, released_htlc, node_a, node_b, now)

	def get_adjusted_amount(self, amount, route):
		'''
			Calculate the payment body, given what the receiver would receive and last hop fees.
			Note: this assumes the last hop only has one channel!
		'''
		# calculate the final receiver amount for a hop
		# which means - subtracting last-hop upfront fee from the given amount
		assert(len(route) >= 2)
		receiver, pre_receiver = route[-1], route[-2]
		direction = (pre_receiver < receiver)
		last_channels_dict = self.ln_model.channel_graph.get_edge_data(receiver, pre_receiver)
		assert(len(last_channels_dict) == 1)
		chosen_cid, chosen_ch_dir = lowest_fee_enabled_channel(last_channels_dict, amount, direction)
		receiver_amount = body_for_amount(amount, chosen_ch_dir.upfront_fee_function)
		return receiver_amount

	def create_payment(self, route, amount, processing_delay, desired_result, enforce_dust_limit):
		'''
			Create a Payment.

			- route
				A list of nodes for the payment to go through.

			- amount
				The amount for the receiver to receive.

			- processing_delay
				How much delay an HTLC created within this payment incurs, if not immediately failed.
				This delay is the same on all hops.

			- desired_result
				Distinguishes honest payments (True) from jams (False).

			- enforce_dust_limit
				Throw an assertion if at any step payment amount is less than the dust limit.

		'''
		#print("Creating a payment for route", route, "and amount", amount)
		p, u_nodes, d_nodes = None, route[:-1], route[1:]
		for u_node, d_node in reversed(list(zip(u_nodes, d_nodes))):
			#print("Wrapping payment w.r.t. fee policy of", u_node, d_node)
			channels_dict = self.ln_model.channel_graph.get_edge_data(u_node, d_node)
			#print("Channels in this hop:", list(channels_dict.keys()))
			chosen_cid, chosen_ch_dir = lowest_fee_enabled_channel(channels_dict, amount, direction=(u_node < d_node))
			#print(chosen_ch_dir)
			is_last_hop = p is None
			p = Payment(
				p,
				d_node,
				chosen_ch_dir.upfront_fee_function,
				chosen_ch_dir.success_fee_function,
				desired_result if is_last_hop else None,
				processing_delay if is_last_hop else None,
				amount if is_last_hop else None)
			if enforce_dust_limit:
				assert(p.amount >= ProtocolParams["DUST_LIMIT"]), (p.amount, ProtocolParams["DUST_LIMIT"])
		#print("Constructed payment:", p)
		return p

	def apply_htlc(self, resolution_time, htlc, u_node, d_node, now):
		'''
			Resolve an HTLC. If (and only if) its desired result is True,
			pass success-case fee from the upstream node to the downstream node.
		'''
		assert(resolution_time <= now)  # must have been checked before popping
		if htlc.desired_result is True:
			#print("Applying", htlc)
			self.ln_model.subtract_revenue(u_node, RevenueType.SUCCESS, htlc.success_fee)
			self.ln_model.add_revenue(d_node, RevenueType.SUCCESS, htlc.success_fee)

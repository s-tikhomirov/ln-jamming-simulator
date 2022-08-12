from lnmodel import LNModel
from schedule import Schedule, Event
from payment import Payment
from channel_selection import lowest_fee_enabled_channel
from lnmodel import RevenueType
from channel import dir0, dir1

from random import random, choice
from string import hexdigits

from params import (
	honest_amount_function,
	honest_proccesing_delay_function,
	honest_generation_delay_function,
	ProtocolParams)

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

	def __init__(self, ln_model):
		# Parse a LN JSON into networkX representation.
		# Assign node IDs and revenues to each node.
		# Assign instances of Channel to each edge according to topology.
		# "open" attacker's channels manually if needed
		self.time = 0
		self.ln_model = ln_model

	def execute_schedule(self,
		schedule,
		simulation_end,
		target_node_pair=None,
		jam_with_insertion=False,
		enforce_dust_limit=True,
		no_balance_failures=False,
		subtract_last_hop_upfront_fee_for_honest_payments=True,
		keep_receiver_upfront_fee=False):
		now, num_events = 0, 0
		#print("Current time:", now)
		while not schedule.schedule.empty():
			new_time, event = schedule.get_event()
			if new_time > now:
				#print("Current time:", new_time)
				pass
			now = new_time
			if now > simulation_end:
				#print("Reached simulation end time.")
				break
			#print("Got event:", event)
			is_jam = event.desired_result == False
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
				# honest senders subtract last hop upfront fee
				# jammers add upfront fees on top of last hop amount
				# to ensure HTLC isn't lower than dust limit
				#print("Subtracting last-hop upfront fee from amount")
				receiver_amount = self.get_adjusted_amount(event.amount, route)
			#print("Receiver will get:", event.amount, "/ in payment body:", receiver_amount)
			p = self.create_payment(route, receiver_amount, event.processing_delay, event.desired_result, enforce_dust_limit)
			#print("Constructed payment:", p)
			reached_receiver, erring_node = self.handle_payment(p, route, now, no_balance_failures, keep_receiver_upfront_fee)
			if is_jam and jam_with_insertion:
				if reached_receiver:
					#print("Jam reached receiver")
					# We just put the same jam back into the queue again!
					# No need to pass around jam amount and jam processing delay.
					#print("Putting this jam into schedule again:", now, event)
					schedule.put_event(now, event)
				elif target_node_pair is not None:
					router_1, router_2 = target_node_pair
					later_time = now + event.processing_delay
					#print("Failed at", erring_node)
					if erring_node == router_2:
						#print("Jam failed at router_2: a balance failure!")
						#print("(Or attacker lacks slots: make sure it has more slots than the victim.)")
						#print("Putting this jam into schedule again:", now, event)
						schedule.put_event(now, event)
					elif erring_node == router_1:
						#print("Jam failed at router_1: victim fully jammed")
						# Note: this may be due to a balance failure, but the jammer doesn't know!
						# If the target channel fails because of balance, it will stay unjammed
						# until the next jamming batch.
						# TODO: implement more complex heuristics of the target being truly jammed.
						# One option: try a few times here, if all of them fail, it's likely jammed.
						# But we can never be certain.
						#print("Putting another jam for later:", later_time, event)
						schedule.put_event(later_time, event)
					else:
						#print("Failed at sender - ... ")
						# make multiple routing attempts?
						pass
			num_events += 1
		#print("Schedule executed.")
		#print("Handled events:", num_events)
		now = simulation_end
		#print("Now is simulation end time:", now)
		# resolve all in-flight htlcs
		#print("Finalizing in-flight HTLCs...")
		self.finalize_in_flight_htlcs(now)
		print("Simulation complete.")
		return num_events

	def get_adjusted_amount(self, amount, route):
		# calculate the final receiver amount for a hop
		# which means - subtracting last-hop upfront fee from the given amount
		assert(len(route) >= 2)
		receiver, pre_receiver = route[-1], route[-2]
		direction = (pre_receiver < receiver)
		# TODO: think how to choose a channel from the sender's point of view
		# calculate fee for given amount
		# choose last-hop channel with lowest fee?
		# for testing, assume just one channel
		last_channels_dict = self.ln_model.channel_graph.get_edge_data(receiver, pre_receiver)
		assert(len(last_channels_dict) == 1)
		last_hop_ch_dir = next(iter(last_channels_dict.values()))["directions"][direction]
		receiver_amount = body_for_amount(amount, last_hop_ch_dir.upfront_fee_function)
		return receiver_amount

	def create_payment(self, route, amount, processing_delay, desired_result, enforce_dust_limit):
		# create a Payment s.t. fee policies are met and receiver gets amount
		#print("Creating a payment for route", route, "and amount", amount)
		p = None
		u_nodes, d_nodes = route[:-1], route[1:]
		for u_node, d_node in reversed(list(zip(u_nodes, d_nodes))):
			#print("Wrapping payment w.r.t. fee policy of", u_node, d_node)
			channels_dict = self.ln_model.channel_graph.get_edge_data(u_node, d_node)
			#print("Channels in this hop:", list(channels_dict.keys()))
			chosen_cid, chosen_ch_dir = lowest_fee_enabled_channel(channels_dict, amount, direction = (u_node < d_node))
			#print(chosen_ch_dir)
			is_last_hop = p is None
			p = Payment(p,
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
		assert(resolution_time <= now)	# must have been checked before popping
		if htlc.desired_result == True:
			#print("Applying", htlc)
			self.ln_model.subtract_revenue(	u_node, RevenueType.SUCCESS, htlc.success_fee)
			self.ln_model.add_revenue(		d_node, RevenueType.SUCCESS, htlc.success_fee)

	def handle_payment(self, payment, route, now, no_balance_failures, keep_receiver_upfront_fee):
		#print("HANDLING PAYMENT", payment.id)

		p = payment
		u_nodes, d_nodes = route[:-1], route[1:]
		erring_node = None

		# store in-flight htlcs here until reached_receiver becomes known
		tmp_cid_to_htlcs = dict()

		for u_node, d_node in list(zip(u_nodes, d_nodes)):

			channels_dict = self.ln_model.channel_graph.get_edge_data(u_node, d_node)
			# select or free a slot, fail if no slots
			# TODO: this doesn't have to be the same function as on payment creation
			# but if it is not, we must check HERE that the payment pays enough fees
			# (or simplify this aspect somehow)
			direction = (u_node < d_node)
			chosen_cid, chosen_ch_dir = lowest_fee_enabled_channel(channels_dict, p.amount, direction)
			#print("Chose channel to forward:", chosen_cid)
			#print(chosen_ch_dir)
			
			if not no_balance_failures:
				# flip coin: fail because of low balance?
				# FIXME: the router doesn't try another channel if one fails, does it?
				amount_plus_upfront_fee = p.amount + p.upfront_fee
				prob_low_balance = amount_plus_upfront_fee / channels_dict[chosen_cid]["capacity"]
				#print("Probability of balance failure:", prob_low_balance)
				if random() < prob_low_balance:
					#print("Low balance - fail payment")
					erring_node = u_node
					break
						
			# check if there are free slots
			success, resolution_time, released_htlc = chosen_ch_dir.ensure_free_slot(now)
			if released_htlc is not None:
				#print("Popped htlc from", u_node, d_node, ":", resolution_time, released_htlc)
				self.apply_htlc(resolution_time, released_htlc, u_node, d_node, now)
			if not success:
				#print("No free slots, failing payment")
				erring_node = u_node
				break

			# account for upfront fee
			self.ln_model.subtract_revenue(	u_node, RevenueType.UPFRONT, p.upfront_fee)
			is_last_hop = d_node == route[-1]
			if not is_last_hop or keep_receiver_upfront_fee:
				self.ln_model.add_revenue(		d_node, RevenueType.UPFRONT, p.upfront_fee)

			# construct a htlc
			in_flight_htlc = InFlightHtlc(p.id, p.success_fee, p.desired_result)
			#print("Constructed htlc:", in_flight_htlc)
			tmp_cid_to_htlcs[(u_node, d_node)] = chosen_cid, direction, now + p.processing_delay, in_flight_htlc

			p = p.downstream_payment

		# reached receiver means we unwrapped the last payment layer
		reached_receiver = p is None
		#print("Reached receiver:", reached_receiver)
		#print("erring_node:", erring_node)
		#print("Temporarily saved htlcs:", tmp_cid_to_htlcs)

		if reached_receiver:
			for u_node, d_node in list(zip(u_nodes, d_nodes)):
				if (u_node, d_node) in tmp_cid_to_htlcs:
					chosen_cid, direction, resolution_time, in_flight_htlc = tmp_cid_to_htlcs[(u_node, d_node)]
					#print("Storing htlc for", chosen_cid, "to resolve at time", resolution_time, ":", in_flight_htlc)
					ch_dir = self.ln_model.channel_graph.get_edge_data(u_node, d_node)[chosen_cid]["directions"][direction]
					ch_dir.store_htlc(resolution_time, in_flight_htlc)

		return reached_receiver, erring_node
		
	def finalize_in_flight_htlcs(self, now):
		# apply all in-flight htlcs with timestamp < now
		# this is done after the simulation is complete
		for (node_a, node_b) in self.ln_model.channel_graph.edges():
			channels_dict = self.ln_model.channel_graph.get_edge_data(node_a, node_b)
			for cid in channels_dict:
				for direction in [dir0, dir1]:
					ch_dir = channels_dict[cid]["directions"][direction]
					if ch_dir is None:
						continue
					time_exceeded = False
					while not ch_dir.slots.empty():
						next_htlc_time = ch_dir.slots.queue[0][0]
						#print("Next HTLC resolution time is:", next_htlc_time)
						if next_htlc_time > now:
							#print("No HTLCs to resolve before current time.")
							break
						resolution_time, released_htlc = ch_dir.slots.get_nowait()
						#print(resolution_time, released_htlc)
						self.apply_htlc(resolution_time, released_htlc, node_a, node_b, now)


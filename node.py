import random

from payment import Payment
from params import ProtocolParams, PaymentFlowParams

class Node:

	def __init__(self,
		name,
		num_slots=ProtocolParams["NUM_SLOTS"],
		prob_next_channel_low_balance=PaymentFlowParams["PROB_NEXT_CHANNEL_LOW_BALANCE"],
		prob_deliberately_fail=0,
		success_fee_function=lambda : 0,
		upfront_fee_function=lambda : 0,
		time_to_next_function=lambda : 1,
		payment_amount_function=None,
		payment_delay_function=None,
		num_payments_in_batch=1,
		subtract_upfront_fee_from_last_hop_amount=True,
		enforce_dust_limit=True
		):
		"""
			A class to represent a node in the network.

			This model doesn't have a Channel class.
			Properties of channels are encoded within Node (this class).

			Attributes:
				name
					The node alias.

				slot_leftovers
					A list that encodes payment slots of the channel
					that precedes this Node in the route.
					E.g.: in A-B-C, B.slot_leftovers are slots in A-B.
					Each value is the number of seconds this slot will be busy
					handling the prior payment after a new payment comes in.
					Only slots with slot_leftover = 0 can take a new payment.

				prob_next_channel_low_balance
					The probability that the _next_ channel in the route has low balance.
					We only model balance probabilistically.
					The probability of failure is constant per node
					(e.g., it doesn't depend on payment amounts).

				prob_deliberately_fail
					The probability that a node will fail a payment
					regardless of whether it can forward it.
					The value is 0 for honest nodes and 1 for jammer-receiver.

				success_fee_function
					A function that calculates success-case fee from payment body.
					Body + success-case fee comprise the payment amount (encoded in HTLC).

				upfront_fee_function
					A function that calculates upfront fee from payment amount (not body!).

				time_to_next_function
					A function that generates a delay until the next payment batch this node sends.
					Only relevant for senders.

				payment_amount_function
					A function that generates a payment amount for new payments.
					Only relevant for senders.
				
				num_payments_in_batch
					The number of payments in a batch. Senders generate payments in batches.
					Delay between payments within a batch is 0 by definition.
					Delay between batches comes from time_to_next_function.
					Jammers send jams in batches of NUM_SLOTS.
					Honest senders send payments in batches of size 1.

				subtract_upfront_fee_from_last_hop_amount
					Whether the upfront fee on the last hop is accounted for at payment creation.
					It should't be counted for honest payments, but should be for jams.
					(Jams' amounts must be above dust limit _excluding_ upfront fee.)

				enforce_dust_limit
					Assert that payment amount is always higher than the dust limit.
		"""
		self.name = name
		self.slot_leftovers = [0] * num_slots
		self.prob_next_channel_low_balance = prob_next_channel_low_balance
		self.prob_deliberately_fail = prob_deliberately_fail
		self.success_fee_function = success_fee_function
		self.upfront_fee_function = upfront_fee_function
		self.time_to_next_function = time_to_next_function
		self.payment_amount_function = payment_amount_function
		self.payment_delay_function = payment_delay_function
		self.num_payments_in_batch = num_payments_in_batch
		self.subtract_upfront_fee_from_last_hop_amount = subtract_upfront_fee_from_last_hop_amount
		self.enforce_dust_limit = enforce_dust_limit
		self.reset()
		
	@staticmethod
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
			#print(amount, body, fee)
			if abs(target_amount - amount) < precision or num_step > max_steps:
				break
			if amount < target_amount:
				min_body = body
			else:
				max_body = body
		return body

	def reset(self):
		"""
			Reset the current revenue, in-flight revenue, and batch progression.
		"""
		self.revenue, self.in_flight_revenue = 0, 0
		self.batch_so_far = 0

	def update_slot_leftovers(self, time_to_next):
		"""
			Move simulated time to the time the next payment comes.
			Slots that are done with the previous payment get assigned leftover = 0 (free).
		"""
		for i,_ in enumerate(self.slot_leftovers):
			self.slot_leftovers[i] = max(0, self.slot_leftovers[i] - time_to_next)

	def next_channel_low_balance(self):
		"""
			Return True if the next channel has low balance to handle this payment.
			We model balance failures probabilistically, the probability is set per node.
		"""
		return random.random() < self.prob_next_channel_low_balance

	def free_slot_indexes(self):
		"""
			Return a list of all indexes of slot_leftovers where the value is 0.
			These slots are free to handle the next incoming payment
		"""
		return [i for i in range(len(self.slot_leftovers)) if self.slot_leftovers[i] == 0]

	def finalize(self, success):
		"""
			If the payment succeeded, add in-flight revenue (i.e., success-case fees)
			to the total revenue of all nodes on the route.
			If the payment failed, nullify in-flight revenue.
		"""
		if success:
			print(self.name, "gets the success-fee difference:", self.in_flight_revenue)
			self.revenue += self.in_flight_revenue
			print(self.name, "'s total revenue now is:", self.revenue)
		self.in_flight_revenue = 0

	def create_payment(self, route):
		"""
			Create a payment for a given route (with random amount and delay).
		"""
		assert(self == route[0])
		receiver = route[-1]
		# jammers add upfront fees on top of last hop amount
		# to ensure HTLC isn't lower than dust limit
		receiver_amount = self.payment_amount_function()
		# honest senders decrease the amount to account for the fact that
		# the receiver also gets the upfront fee
		if self.subtract_upfront_fee_from_last_hop_amount:
			receiver_amount = self.body_for_amount(receiver_amount, receiver.upfront_fee_function)
		delay = self.payment_delay_function()
		p = Payment(None, receiver.upfront_fee_function, receiver.success_fee_function, 
			delay=delay, receiver_amount=receiver_amount)
		if self.enforce_dust_limit:
			assert(p.amount >= ProtocolParams["DUST_LIMIT"]), (p.amount, ProtocolParams["DUST_LIMIT"])
		for node in reversed(route[:-2]):
			p = Payment(p, node.upfront_fee_function, receiver.success_fee_function)
			if self.enforce_dust_limit:
				assert(p.amount >= ProtocolParams["DUST_LIMIT"]), (p.amount, ProtocolParams["DUST_LIMIT"])
		return p

	def time_to_next(self):
		"""
			Time in seconds until the next payment (within one batch, delay = 0).
		"""
		self.batch_so_far += 1
		if self.batch_so_far >= self.num_payments_in_batch:
			self.batch_so_far = 0
			time_to_next = self.time_to_next_function()
		else:
			time_to_next = 0
		return time_to_next

	def route_payment(self, outermost_payment, route):
		"""
			Process one payment.

			Arguments:
				
				outermost_payment
					The payment to process, as setup by the first node (the sender).

				route
					A list of nodes.
					The route must be the same as at payment creation.

			Returns:

				success
					Payment result: success or fail.

				time_to_next
					Time until the next payment

			This function also updates revenues for nodes on the route.
		"""

		# sanity checks
		assert(route[0] == self)
		assert(len(route) >= 2)
		# payment means the current-level payment
		payment = outermost_payment
		success = True
		for i in range(len(route)):
			node = route[i]

			print()
			print(node.name, "considers payment:")
			print(payment)

			# decide whether this node deliberately fails the payment
			# if it does, no further checks are necessary
			deliberately_fail = random.random() < node.prob_deliberately_fail
			#print(node.name, "will deliberately fail the payment?", deliberately_fail)
			if deliberately_fail:
				print(node.name, "deliberately fails the payment")
				success = False
				break

			# check if the current node is the receiver
			# if so, the payment succeeds - no further forwarding needed
			# note: honest receiver never deliberately fails payments
			# if it were the jammer-receiver, fail would have happened earlier
			node_is_receiver = (i == len(route) - 1)
			if node_is_receiver:
				print("Payment reaches the receiver:", node.name)
				# we nullify receiver's revenue because its upfront fee
				# was excluded from final amount when creating the payment
				node.revenue = 0
				assert(node.in_flight_revenue == 0)
				break

			# now the node intends to forward the payment
			# check if the next balance is sufficient
			#print(node.name, "checks next balance")
			low_balance = node.next_channel_low_balance()
			print("Next channel has low balance?", low_balance)

			# consider the next node (it exists because node is not the receiver)	
			next_node = route[i+1]
			print("Next node is", next_node.name)
			# check if the _next_ node (i.e., channel) has free slots
			print(node.name, "checks next channel's slots")
			no_slots = len(next_node.free_slot_indexes()) == 0
			print("Next channel has no slots?", no_slots)

			if low_balance or no_slots:
				print(node.name, "fails the payment")
				success = False
				break
			
			# actually start forwarding payment
			print("\n", node.name, "forwards the payment")

			# account for upfront fee
			print(node.name, "pays upfront fee:", payment.upfront_fee)
			node.revenue -= payment.upfront_fee
			print(next_node.name, "receives upfront fee:", payment.upfront_fee)
			next_node.revenue += payment.upfront_fee

			# block a slot in the current ("previous") channel
			print("Occupying a slot for payment delay:", payment.delay)
			chosen_slot = node.free_slot_indexes()[0]
			node.slot_leftovers[chosen_slot] += payment.delay

			# add success fee to in-flight revenue
			print(node.name, "may later pay success fee:", payment.success_fee)
			node.in_flight_revenue -= payment.success_fee
			print(next_node.name, "may later receive success fee:", payment.success_fee)
			next_node.in_flight_revenue += payment.success_fee

			payment = payment.downstream_payment
						
		time_to_next = self.time_to_next()
		print("Time to next", time_to_next)
		print()
		for node in route:
			node.finalize(success)
			node.update_slot_leftovers(time_to_next)

		if success:
			print("Payment complete!")
			pass

		return success, time_to_next

	
	def __str__(self):
		s = ""
		s += self.name + "'s revenue: 	" + str(self.revenue)
		return s


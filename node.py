import random

from payment import Payment

class Node:

	def __init__(self, name, num_slots=1,
		prob_next_channel_low_balance=0,
		prob_deliberately_fail=0,
		success_fee_function=lambda a: 0, upfront_fee_function=lambda a: 0,
		time_to_next_function=None, payment_amount_function=None, payment_delay_function=None,
		num_payments_in_batch=1):
		self.name = name
		self.slot_leftovers = [0] * num_slots
		# probabilty with which this node fails payments for reasons OTHER THAN "no free slots"
		self.prob_next_channel_low_balance = prob_next_channel_low_balance
		self.prob_deliberately_fail = prob_deliberately_fail
		self.success_fee_function = success_fee_function
		self.upfront_fee_function = upfront_fee_function
		# time_to_next_function is only defined for the sender
		self.time_to_next_function = time_to_next_function
		self.payment_amount_function = payment_amount_function
		self.payment_delay_function = payment_delay_function
		self.num_payments_in_batch = num_payments_in_batch
		self.reset()
		
	def reset(self):
		self.revenue, self.in_flight_revenue = 0, 0
		self.batch_so_far = 0

	def update_slot_leftovers(self, time_to_next):
		for i,_ in enumerate(self.slot_leftovers):
			self.slot_leftovers[i] = max(0, self.slot_leftovers[i] - time_to_next)

	def next_channel_low_balance(self):
		network_fail = random.random() < self.prob_next_channel_low_balance
		return network_fail

	def chosen_free_slot(self):
		free_slots = [i for i in range(len(self.slot_leftovers)) if self.slot_leftovers[i] == 0]
		if len(free_slots) > 0:
			chosen_slot = free_slots[0]
			return chosen_slot
		return None

	def has_no_slots(self):
		# we use this to check if the _next_ channel has slots before forwarding
		return not (0 in self.slot_leftovers)

	def finalize(self, success):
		#print("Finalizing for", self.name)
		if success:
			print(self.name, "gets the success-fee difference:", self.in_flight_revenue)
			self.revenue += self.in_flight_revenue
			print(self.name, "'s total revenue now is:", self.revenue)
		self.in_flight_revenue = 0

	def create_payment(self, route):
		#print(self.name, "created a payment")
		assert(self == route[0])
		receiver = route[-1]
		amount = self.payment_amount_function()
		delay = self.payment_delay_function()
		p = Payment(None, receiver.upfront_fee_function, receiver.success_fee_function, 
			delay=delay, body=amount)
		for node in reversed(route[:-2]):
			p = Payment(p, node.upfront_fee_function, receiver.success_fee_function)
		return p

	def time_to_next(self):
		self.batch_so_far += 1
		if self.batch_so_far >= self.num_payments_in_batch:
			self.batch_so_far = 0
			time_to_next = self.time_to_next_function()
		else:
			time_to_next = 0
		return time_to_next

	def route_payment(self, outermost_payment, route):
		# sanity checks
		sender = route[0]
		assert(sender == self)
		assert(len(route) >= 2)

		payment = outermost_payment
		for i in range(len(route)):

			node = route[i]

			print()
			print(node.name, "considers payment:")
			print(payment)

			# if this node deliberately fails, no further checks happen
			deliberately_fail = random.random() < node.prob_deliberately_fail
			print(node.name, "will deliberately fail the payment?", deliberately_fail)
			if deliberately_fail:
				print(node.name, "deliberately failed the payment")
				success = False
				break

			# if this is the receiver, payment succeeds
			node_is_last = (i == len(route) - 1)
			if node_is_last:
				# deliberate failuer must have been checked earlier
				print("Payment reached the receiver:", node.name)
				success = True
				break

			# this node is not the receiver and intends to forward
			print(node.name, "checks next balance")
			low_balance = node.next_channel_low_balance()
			print("Next channel has low balance?", low_balance)

			next_node = route[i+1]
			print("Next node is", next_node.name)

			print(node.name, "checks next channel's slots")
			no_slots = next_node.has_no_slots()
			print("Next channel has no slots?", no_slots)

			success = not low_balance and not no_slots

			if not success:
				print(node.name, "failed the payment")
				break
			
			# actually start forwarding payment
			print("\n", node.name, "forwards the payment")

			# upfront fee
			print(node.name, "pays upfront fee:", payment.upfront_fee)
			node.revenue -= payment.upfront_fee
			print(next_node.name, "receives upfront fee:", payment.upfront_fee)
			next_node.revenue += payment.upfront_fee

			# block a slot in the previous channel
			print("Occupying a slot for payment delay:", payment.delay)
			chosen_slot = node.chosen_free_slot()
			node.slot_leftovers[chosen_slot] += payment.delay

			# success fee to in-flight revenue
			print(node.name, "may later pay success fee:", payment.success_fee)
			node.in_flight_revenue -= payment.success_fee
			print(next_node.name, "may later receive success fee:", payment.success_fee)
			next_node.in_flight_revenue += payment.success_fee

			payment = payment.downstream_payment
						
		time_to_next = self.time_to_next()
		print("Time to next", time_to_next)
		print()
		for node in route:
			# FIXME: don't count upfront fee as revenue for receiver?
			# doesn't matter as long as we're only looking at Router's revenue
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


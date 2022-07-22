import random

from payment import Payment

class Node:

	def __init__(self, name, num_slots=1, prob_next_channel_fail=0,
		success_fee_function=lambda a: 0, upfront_fee_function=lambda a: 0,
		time_to_next_function=None, payment_amount_function=None, payment_delay_function=None,
		num_payments_in_batch=1):
		self.name = name
		self.slot_leftovers = [0] * num_slots
		# probabilty with which this node fails payments for reasons OTHER THAN "no free slots"
		self.prob_next_channel_fail = prob_next_channel_fail
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

	def get_free_slots(self):
		return [i for i in range(len(self.slot_leftovers)) if self.slot_leftovers[i] == 0]

	def update_slot_leftovers(self, time_to_next):
		for i,_ in enumerate(self.slot_leftovers):
			self.slot_leftovers[i] = max(0, self.slot_leftovers[i] - time_to_next)

	def next_channel_will_fail(self):
		network_fail = random.random() < self.prob_next_channel_fail
		return network_fail

	def chosen_free_slot(self):
		free_slots = self.get_free_slots()
		if len(free_slots) > 0:
			chosen_slot = free_slots[0]
			return chosen_slot
		return None

	def handle(self, payment):
		#print(payment)
		success_so_far = False
		chosen_slot = self.chosen_free_slot()
		do_handle = chosen_slot is not None and not self.next_channel_will_fail()
		if do_handle:
			print(self.name, "takes upfront fee:", payment.upfront_fee)
			self.revenue += payment.upfront_fee
			self.slot_leftovers[chosen_slot] += payment.delay
			success_so_far = True
			ds_payment = payment.downstream_payment
			if ds_payment is not None:
				assert(payment.upfront_fee >= ds_payment.upfront_fee)
				assert(payment.success_fee >= ds_payment.success_fee)
				print(self.name, "pays upfront fee:", ds_payment.upfront_fee)
				self.revenue -= ds_payment.upfront_fee
				print(self.name, "'s revenue now is:", self.revenue)
				self.in_flight_revenue += (payment.success_fee - ds_payment.success_fee)
				print("Payment succeeds so far")
			else:
				print("Payment reached the receiver")
				pass
		else:
			print("Payment failed")
			pass
		return success_so_far

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

	def route_payment(self, payment, route):
		sender = route[0]
		assert(sender == self)
		print("\n", sender.name, "sends payment:")
		print(payment)
		success = not self.next_channel_will_fail()
		if not success:
			print(self.name, "failed the payment")
			if self.name == "Sender":
				print("sender failed the payment")
				exit()
			pass
		else:
			# the sender pays upfront fee in any case
			print(sender.name, "pays upfront fee:", payment.upfront_fee)
			sender.revenue -= payment.upfront_fee
			# the sender will (maybe) pay success fee later
			#print(sender.name, "may later pay success-case fee:", payment.success_fee)
			sender.in_flight_revenue -= payment.success_fee
			current_payment = payment
			for node in route[1:]:
				print(node.name, "handles payment")
				success = node.handle(current_payment)
				if not success:
					print("Fail at node", node.name)
					success = False
					break
				current_payment = current_payment.downstream_payment
		time_to_next = self.time_to_next()
		print("Time to next", time_to_next)
		print()
		for node in route:
			# FIXME: don't count upfront fee as revenue for receiver?
			# doesn't matter as long as we're only looking at Router's revenue
			node.finalize(success)
			node.update_slot_leftovers(time_to_next)
		return success, time_to_next
	
	def __str__(self):
		s = ""
		s += self.name + "'s revenue: 	" + str(self.revenue)
		return s


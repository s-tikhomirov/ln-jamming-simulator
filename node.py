import random

class Node:

	def __init__(self, name, fee_policy, num_slots, prob_network_fail=0, prob_deliberate_fail=0):
		self.name = name
		self.fee_policy = fee_policy
		# probabilty with which this node fails payments for reasons OTHER THAN "no free slots"
		self.prob_network_fail = prob_network_fail
		# probability with which node fails payments deliberately (i.e., jammer-receiver)
		self.prob_deliberate_fail = prob_deliberate_fail
		self.slot_leftovers = [0] * num_slots
		self.reset()
		
	def reset(self):
		self.revenue, self.amount_forwarded, self.total_payments, self.failed_payments = 0, 0, 0, 0

	def get_free_slots(self):
		return [i for i in range(len(self.slot_leftovers)) if self.slot_leftovers[i] == 0]

	def update_slot_leftovers(self, time_to_next):
		for i,_ in enumerate(self.slot_leftovers):
			self.slot_leftovers[i] = max(0, self.slot_leftovers[i] - time_to_next)

	def handle(self, payment):
		self.total_payments += 1
		self.revenue += payment.upfront_fee
		free_slots = self.get_free_slots()
		success_so_far = False
		if len(free_slots) > 0:
			chosen_slot = free_slots[0]
			self.slot_leftovers[chosen_slot] += payment.delay
			# if nodes deliberately fail payments, this happens here
			network_fail = random.random() < self.prob_network_fail
			deliberate_fail = random.random() < self.prob_deliberate_fail
			if not network_fail and not deliberate_fail:
				ds_payment = payment.downstream_payment
				self.revenue -= ds_payment.upfront_fee
				self.amount_forwarded += ds_payment.amount
				self.revenue += (payment.success_fee - ds_payment.success_fee)
				success_so_far = True
		if not success_so_far:
			self.failed_payments += 1
		return success_so_far

	
	def __str__(self):
		s = ""
		s = "Node " + self.name
		s += "\nPayments handled: 	" + str(self.total_payments)
		s += "\n	of them failed: " + str(self.failed_payments)
		if self.total_payments > 0:
			s += "\nShare of failed:	" + str(round(self.failed_payments / self.total_payments, 4))
		s += "\n\nValue forwarded: 	" + str(self.amount_forwarded)
		s += "\nRevenue: 		" + str(self.revenue)
		if self.amount_forwarded > 0:
			s += "\nRevenue to value:	" + str(round(self.revenue / self.amount_forwarded, 4))
		if self.total_payments > 0:
			s += "\n  per payment handled:	" + str(round(self.revenue / self.total_payments))
		return s


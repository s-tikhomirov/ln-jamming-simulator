class Node:

	def __init__(self, name, fee_policy, num_slots):
		self.name = name
		self.fee_policy = fee_policy
		self.slot_leftovers = [0] * num_slots
		self.reset()
		
	def reset(self):
		self.revenue, self.amount_forwarded, self.total_payments, self.failed_payments = 0, 0, 0, 0

	def set_fee_policy(self, new_fee_policy):
		self.fee_policy = new_fee_policy

	def get_free_slots(self):
		return [i for i in range(len(self.slot_leftovers)) if self.slot_leftovers[i] == 0]

	def update_slot_leftovers(self, time_to_next):
		for i,_ in enumerate(self.slot_leftovers):
			self.slot_leftovers[i] = max(0, self.slot_leftovers[i] - time_to_next)

	def handle(self, payment_batch):
		self.total_payments += 1
		free_slots = self.get_free_slots()
		if len(free_slots) >= len(payment_batch):
			for i,_ in enumerate(payment_batch):
				payment = payment_batch[i]
				chosen_slot = free_slots[i]
				self.slot_leftovers[chosen_slot] += payment.delay
				# should we add discarded payments to total?
				self.total_payments += 1
				#print("adding incoming upfront fee", payment.upfront_fee)
				self.revenue += payment.upfront_fee
				success_so_far = True
				self.forward(payment)
		else:
			success_so_far = False
		return success_so_far

	def forward(self, payment):
		ds_payment = payment.ds_payment
		#print("subreacting downstream upfront fee", ds_payment.upfront_fee)
		self.revenue -= ds_payment.upfront_fee
		if ds_payment.success:
			self.amount_forwarded += ds_payment.amount
			#print("adding diff between success_fees:", payment.success_fee, ds_payment.success_fee)
			self.revenue += (payment.success_fee - ds_payment.success_fee)
		else:
			self.failed_payments += 1
	
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


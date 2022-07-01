class Node:

	def __init__(self, name, fee_policy):
		self.name = name
		self.fee_policy = fee_policy
		self.reset()
		
	def reset(self):
		self.revenue, self.amount_forwarded, self.total_payments, self.failed_payments = 0, 0, 0, 0

	def set_fee_policy(self, new_fee_policy):
		self.fee_policy = new_fee_policy

	def handle(self, payment, forward=True):
		# should we add discarded payments to total?
		self.total_payments += 1
		#print("adding incoming upfront_fee", payment.upfront_fee)
		self.revenue += payment.upfront_fee
		if forward:
			# forward payment
			self.forward(payment)
		else:
			# discard payment
			pass

	def forward(self, payment):
		ds_payment = payment.ds_payment
		#print("subreacting ds fee", ds_payment.upfront_fee)
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


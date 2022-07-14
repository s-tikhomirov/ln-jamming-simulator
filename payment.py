class Payment:
	'''
		A payment has amount, fee(s), and the next payment.
	'''
	def __init__(self, downstream_payment, fee_policy, amount=None, delay=None):
		self.downstream_payment = downstream_payment
		if downstream_payment is None:
			# we're at the last hop
			assert(amount is not None and delay is not None)
			self.amount = amount
			self.upfront_fee = 0
			self.success_fee = 0
			self.delay = delay
		else:
			# amount is fully deteremined by downstream payment
			self.amount = (
				downstream_payment.amount + 
				downstream_payment.upfront_fee + 
				downstream_payment.success_fee)
			self.upfront_fee, self.success_fee = fee_policy.calculate_fees(self.amount)
			self.delay = downstream_payment.delay

	def __str__(self):
		total_fee = self.upfront_fee + self.success_fee
		s = "\nAmount:  " + str(self.amount)
		if self.downstream_payment is not None:
			s += "\n  Total fee:	" + str(total_fee) \
			#+ "\n    in %:	" + str(round(100 * total_fee / self.amount))
			s += "\n  upfront fee:	" + str(self.upfront_fee)
			s += "\n  success_fee:	" + str(self.success_fee)
			s += "  \nDownstream payment:"
			s += str(self.downstream_payment)
		#s += "\nContains downstream Payment? " + str(self.downstream_payment is not None)
		return s



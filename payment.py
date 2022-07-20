'''
	A Payment encodes the channel state update between two nodes.
'''
class Payment:
	
	def __init__(self, downstream_payment, upfront_fee_function, success_fee_function, 
		delay=None, body=None):
		assert(downstream_payment is None or body is None and delay is None)
		self.downstream_payment = downstream_payment
		if downstream_payment is None:
			# we are in the innermost layer of the onion
			# this payment is from pre-last to last node
			# we calculate the "fixed" body such that:
			# amount + upfront fee = (final) body
			self.body = self.fixed_final_body(body, upfront_fee_function)
			# success-case fee is zero by definition
			self.success_fee = 0
			self.delay = delay
		else:
			# we are in the middle of the route
			self.body = downstream_payment.amount
			# success-case fee is calculated from the BODY (i.e., downstream payment's amount)
			self.success_fee = success_fee_function(self.body)
			# we just copy the delay over through layers to have quick access to it
			# no matter where the payment fails
			# TODO: implement incremental delays at each hop
			self.delay = downstream_payment.delay
		# amount = body + success-case fee (by definition!)
		# amount is how much is encoded in the HTLC
		self.amount = self.body + self.success_fee
		# therefore, upfront-fee is calculated based on the AMOUNT, not body
		self.upfront_fee = upfront_fee_function(self.amount)
		
	@staticmethod
	def fixed_final_body(target_amount, upfront_fee_function, precision=1):
		'''
			Given target_amount and fee function, find a such that:
			a + fee(a) = target_amount
		'''
		min_b, max_b = 0, target_amount
		while True:
			b = round((min_b + max_b) / 2)
			f = upfront_fee_function(b)
			a = b + f
			if abs(a - target_amount) < precision:
				break
			if a < target_amount:
				min_b = b
			else:
				max_b = b
		return b

	def __str__(self):
		s = "\nPayment with amount: 	" + str(self.amount)
		s += "\n  of which body:	" + str(self.body)
		s += "\n  success-case fee:	" + str(self.success_fee)
		s += "\nUpfront fee: 		" + str(self.upfront_fee)
		s += "\nAmount + upfront_fee:	" + str(self.amount + self.upfront_fee)
		s += "\nDownstream payment:	" + str(self.downstream_payment)
		if self.downstream_payment is None:
			s += "\nDelay:			" + str(self.delay)
		return s


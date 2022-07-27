from params import ProtocolParams

'''
	A Payment encodes the channel state update between two nodes.
'''
class Payment:
	
	def __init__(self,
		downstream_payment,
		upfront_fee_function,
		success_fee_function, 
		delay=None,
		receiver_amount=None):
		"""
			Construct a payment.

			A payment represents value transfers within one hop.
			A payment is 'nested': a payment contains the downstream payment.
			For the inner-most payment, downstream payment is None.

			Attributes:

				downstream_payment
					A Payment to be forwarded to the next node in the route.

				upfront_fee_function
					A function to calculate the upfront fee from payment _amount_.
					(Amount = body + success-case fee.)

				success_fee_function
					A function to calculate the success-case fee from the payment _body_.

				delay
					How much a payment takes to process.
					Delay is copied over through all payment layers.
					In our model, a payment incurs the same delay on all hops in the route.

				receiver_amount
					How much the receiver will get if the payment succeeds.

		"""
		# for the last node, there is no downstream payment
		is_last_hop = downstream_payment is None
		# for an intermediary node, the final amount and delay are already determined
		is_not_last_hop = receiver_amount is None and delay is None
		# make sure that given arguments are not contradictory w.r.t. last or not-last hop
		assert(is_last_hop or is_not_last_hop)
		self.downstream_payment = downstream_payment
		if is_last_hop:
			# this might have been adjusted by the sender to exclude upfront fee
			self.body = receiver_amount
			# success-case fee for the last hop is zero by definition
			self.success_fee = 0
			self.delay = delay
		else:
			# this hop's payment body is the downstream payment amount
			self.body = downstream_payment.amount
			# success-case fee is calculated based on _body_
			self.success_fee = success_fee_function(self.body)
			# copy over the delay from downstream payment
			self.delay = downstream_payment.delay
		# amount = body + success-case fee (by definition!)
		# amount is how much is encoded in the HTLC
		self.amount = self.body + self.success_fee
		# upfront-fee is calculated based on the _amount_
		self.upfront_fee = upfront_fee_function(self.amount)
		

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

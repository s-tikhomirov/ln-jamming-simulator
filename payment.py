from random import random, choice
from string import hexdigits

'''
	A Payment encodes the channel state update between two nodes.
'''
class Payment:
	'''
		A Payment is a nested data structure.
		The outermost layer encodes value transfers in the next Channel
		(related to the Node that unpacks the Payment).
		The next nested Payment is forwarded to the next Node on the route.
		We don't need payment_id: after payment is forwarded,
		the only important thing is when it resolves (timestamp).
		A Payment contains:
		- payment Id (for debugging mostly)
		- amount = body plus success-case fee
		- upfront fee
		- processing delay
		- desired result
	'''
	
	def __init__(self,
		downstream_payment,
		upfront_fee_function,
		success_fee_function,
		desired_result=None,
		processing_delay=None,
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

				desired_result
					True for honest payments, False for jams.
				
				success_fee_function
					A function to calculate the success-case fee from the payment _body_.

				processing_delay
					How much a payment takes to process.
					Delay is copied over through all payment layers.
					In our model, a payment incurs the same processing delay on all hops in the route.

				receiver_amount
					How much the receiver will get if the payment succeeds.

		"""
		# for the last node, there is no downstream payment
		is_last_hop = downstream_payment is None
		# for an intermediary node, the final amount and processing delay are already determined
		is_not_last_hop = desired_result is None and receiver_amount is None and processing_delay is None
		# make sure that given arguments are not contradictory w.r.t. last or not-last hop
		assert(is_last_hop or is_not_last_hop)
		self.downstream_payment = downstream_payment
		if is_last_hop:
			self.id = "".join(choice(hexdigits) for i in range(6))
			# this might have been adjusted by the sender to exclude upfront fee
			self.body = receiver_amount
			# success-case fee for the last hop is zero by definition
			self.success_fee = 0
			self.processing_delay = processing_delay
			self.desired_result = desired_result
		else:
			self.id = downstream_payment.id
			# this hop's payment body is the downstream payment amount
			self.body = downstream_payment.amount
			# success-case fee is calculated based on _body_
			self.success_fee = success_fee_function(self.body) + downstream_payment.success_fee
			# copy over the processing delay from downstream payment
			self.processing_delay = downstream_payment.processing_delay
			self.desired_result = downstream_payment.desired_result
		# amount = body + success-case fee (by definition!)
		# amount is how much is encoded in the HTLC
		# TODO: we don't have to store body and success_fee separately at every onion level
		# we do so here only for clearer printing
		# may remove when everything is debugged
		self.amount = self.body + self.success_fee
		# upfront-fee is calculated based on the _amount_
		downstream_upfront_fee = 0 if downstream_payment is None else downstream_payment.upfront_fee
		self.upfront_fee = upfront_fee_function(self.amount) + downstream_upfront_fee
		

	def __str__(self):
		s = "\nPayment with amount: 	" + str(self.amount)
		s += "\n  of which body:	" + str(self.body)
		s += "\n  success-case fee:	" + str(self.success_fee)
		s += "\nUpfront fee: 		" + str(self.upfront_fee)
		s += "\nAmount + upfront_fee:	" + str(self.amount + self.upfront_fee)
		s += "\nDownstream payment:	" + str(self.downstream_payment)
		if self.downstream_payment is None:
			s += "\nProcessing delay:	" + str(self.processing_delay)
		return s

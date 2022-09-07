from utils import generate_id

import logging
logger = logging.getLogger(__name__)


class Payment:
	'''
		A Payment encodes the channel state update between two nodes.
		A payment is 'nested': a payment contains the downstream payment.
		For the inner-most payment, downstream payment is None.
	'''

	def __init__(
		self,
		downstream_payment,
		downstream_node,
		upfront_fee_function,
		success_fee_function,
		desired_result=None,
		processing_delay=None,
		last_hop_body=None):
		'''
			Attributes:

				- downstream_payment
					A Payment to be forwarded to the next node in the route.

				- downstream_node
					A node to forward the payment to.

				- upfront_fee_function
					A function to calculate the upfront fee from payment _amount_.
					(Amount = body + success-case fee.)

				- success_fee_function
					A function to calculate the success-case fee from the payment _body_.

				- desired_result
					True for honest payments, False for jams.

				- processing_delay
					How much a payment takes to process.
					A payment incurs the same processing delay on all hops in the route.
					Delay is incurred if (and only if) the payment reaches the receiver.

				- last_hop_body
					How much the receiver will get if the payment succeeds.

		'''
		# for the last node, there is no downstream payment
		is_last_hop = downstream_payment is None
		# for an intermediary node, the desired result, final amount, and processing delay are already determined
		is_not_last_hop = desired_result is None and last_hop_body is None and processing_delay is None
		# make sure that given arguments are not contradictory
		assert is_last_hop or is_not_last_hop
		self.downstream_payment = downstream_payment
		self.downstream_node = downstream_node
		if is_last_hop:
			logger.debug(f"Receiver will get {last_hop_body} (without fees)")
			assert last_hop_body > 0
			self.id = generate_id()
			# this might have been adjusted by the sender to exclude upfront fee
			self.body = last_hop_body
			# success-case fee for the last hop is zero by definition
			self.success_fee = 0
			self.processing_delay = processing_delay
			self.desired_result = desired_result
		else:
			self.id = downstream_payment.id
			# this hop's payment body is the downstream payment amount
			self.body = downstream_payment.get_amount()
			# success-case fee is calculated based on BODY
			self.success_fee = success_fee_function(self.body) + downstream_payment.success_fee
			# copy over the processing delay from downstream payment
			self.processing_delay = downstream_payment.processing_delay
			self.desired_result = downstream_payment.desired_result
		# upfront-fee is calculated based on AMOUNT
		downstream_upfront_fee = 0 if downstream_payment is None else downstream_payment.upfront_fee
		self.upfront_fee = upfront_fee_function(self.get_amount()) + downstream_upfront_fee

	def get_amount(self):
		return self.body + self.success_fee

	def get_amount_plus_upfront_fee(self):
		return self.get_amount() + self.upfront_fee

	def __repr__(self):  # pragma: no cover
		s = "\nPayment with amount: 	" + str(self.amount)
		s += "\n  of which body:	" + str(self.body)
		s += "\n  success-case fee:	" + str(self.success_fee)
		s += "\nTo node:		" + str(self.downstream_node)
		s += "\nUpfront fee: 		" + str(self.upfront_fee)
		s += "\nAmount + upfront_fee:	" + str(self.amount + self.upfront_fee)
		s += "\nDownstream payment:	" + str(self.downstream_payment)
		if self.downstream_payment is None:
			s += "\nProcessing delay:	" + str(self.processing_delay)
		return s

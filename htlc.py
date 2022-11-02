import logging
logger = logging.getLogger(__name__)


class Htlc:
	'''
		An in-flight HTLC.
		Note: we don't model balances.
		An HTLC only contains success-case fee, and doesn't include the payment amount.
	'''

	def __init__(self, payment_id, success_fee, desired_result):
		'''
			- payment_id
				Payment identifier (randomly generated).

			- success_fee
				Success-case fee to be paid if the payment resolves and its desired result is True.

			- desired_result
				Determines the behavior if the payment reaches the receiver.
				True for honest payments, False for jams.
		'''
		self.payment_id = payment_id
		self.success_fee = success_fee
		self.desired_result = desired_result

	def __lt__(self, other):
		return self.payment_id < other.payment_id

	def __gt__(self, other):
		return other < self

	def __repr__(self):  # pragma: no cover
		s = str((self.payment_id, self.success_fee, self.desired_result))
		return s

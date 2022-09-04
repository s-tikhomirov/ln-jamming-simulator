import logging
logger = logging.getLogger(__name__)


class InFlightHtlc:
	'''
		An in-flight HTLC.
		As we don't model balances, an HTLC only contrains success-case fee.
	'''

	def __init__(self, payment_id, success_fee, desired_result):
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

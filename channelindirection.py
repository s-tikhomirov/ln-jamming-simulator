from queue import PriorityQueue
from functools import partial

from enumtypes import ErrorType, FeeType
from params import generic_fee_function

import logging
logger = logging.getLogger(__name__)


class ChannelInDirection:
	'''
		A ChannelInDirection models a Channel's forwarding process in one direction.
	'''

	def __init__(
		self,
		num_slots,
		upfront_base_fee=0,
		upfront_fee_rate=0,
		success_base_fee=0,
		success_fee_rate=0,
		deliberately_fail_prob=0,
		spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		'''
			- num_slots
				The max size of a PriorityQueue of in-flight HTLCs.
				The queue priority metric is HTLC resolution time.

			- upfront_base_fee
				A base fee for upfront fee function.

			- upfront_fee_rate
				A rate for upfront fee function.

			- success_base_fee
				A base fee for success-case fee function.

			- success_fee_rate
				A rate for upfront fee function.

			- deliberately_fail_prob
				The probability with which this ch_in_dir deliberately fails payments
				(before making any other checks, like balance or slot checks).

			- spoofing_error_type
				The error type to return when deliberately failing a payment.
		'''
		self.set_fee(FeeType.UPFRONT, upfront_base_fee, upfront_fee_rate)
		self.set_fee(FeeType.SUCCESS, success_base_fee, success_fee_rate)
		self.reset_slots(num_slots)
		self.deliberately_fail_prob = deliberately_fail_prob
		self.spoofing_error_type = spoofing_error_type

	def set_fee(self, fee_type, base_fee, fee_rate):
		fee_function = partial(lambda a: generic_fee_function(base_fee, fee_rate, a))
		if fee_type == FeeType.UPFRONT:
			self.upfront_base_fee = base_fee
			self.upfront_fee_rate = fee_rate
			self.upfront_fee_function = fee_function
		elif fee_type == FeeType.SUCCESS:
			self.success_base_fee = base_fee
			self.success_fee_rate = fee_rate
			self.success_fee_function = fee_function

	def reset_slots(self, num_slots=None):
		# Initialize slots to a PriorityQueue of a given maxsize.
		# (An existing queue cannot be re-sized.)
		# Store num_slots in a separate variable:
		# we can't get it from a queue after it's created.
		if num_slots is not None:
			assert num_slots > 0
			self.num_slots = num_slots
		else:
			assert self.num_slots is not None
		self.slots = PriorityQueue(maxsize=self.num_slots)

	def all_slots_busy(self):
		return self.slots.full()

	def all_slots_free(self):
		return self.slots.empty()

	def is_jammed(self, time):
		return self.all_slots_busy() and self.get_top_timestamp() > time

	def get_num_slots(self):
		return self.num_slots

	def get_num_slots_occupied(self):
		# Note: this doesn't reflect that some slots may be occupied by outdated HTLCs!
		return self.slots.qsize()

	def get_num_slots_free(self):
		return self.get_num_slots() - self.get_num_slots_occupied()

	def get_top_timestamp(self):
		assert not self.all_slots_free()
		return self.slots.queue[0][0]

	def requires_fee_for_body(self, fee_type, body, zero_success_fee=False):
		success_fee = 0 if zero_success_fee else self.success_fee_function(body)
		if fee_type == FeeType.UPFRONT:
			amount = body + success_fee
			return self.upfront_fee_function(amount)
		elif fee_type == FeeType.SUCCESS:
			return success_fee

	def requires_total_fee_for_body(self, body, zero_success_fee=False):
		return (
			self.requires_fee_for_body(FeeType.UPFRONT, body, zero_success_fee)
			+ self.requires_fee_for_body(FeeType.SUCCESS, body, zero_success_fee))

	def requires_fee(self, fee_type, payment, zero_success_fee=False):
		# Last hop in route charges zero success fee by definition: next node does not have to forward anything.
		# Upfront fee, however, is still being paid, even on the last hop!
		# (It may have been subtracted from the amount at payment creation.)
		return self.requires_fee_for_body(fee_type, payment.get_body(), zero_success_fee)

	def requires_total_fee(self, payment, zero_success_fee=False):
		return (
			self.requires_fee(FeeType.SUCCESS, payment, zero_success_fee)
			+ self.requires_fee(FeeType.UPFRONT, payment, zero_success_fee))

	def enough_fee(self, fee_type, payment, zero_success_fee=False):
		return payment.pays_fee(fee_type) >= self.requires_fee(fee_type, payment, zero_success_fee)

	def enough_total_fee(self, payment, zero_success_fee=False):
		return (
			self.enough_fee(FeeType.SUCCESS, payment, zero_success_fee)
			and self.enough_fee(FeeType.UPFRONT, payment, zero_success_fee))

	def pop_htlc(self):
		assert not self.all_slots_free()
		resolution_time, htlc = self.slots.get_nowait()
		return resolution_time, htlc

	def push_htlc(self, resolution_time, in_flight_htlc):
		# Store an in-flight HTLC in the slots queue.
		# The queue must not be full!
		# We must have ensured a free slot earlier.
		assert not self.all_slots_busy()
		self.slots.put_nowait((resolution_time, in_flight_htlc))

	def ensure_free_slots(self, time, num_slots_needed):
		# TODO: do we ever need to ensure more than one slot at a time?
		# Ensure there are num_slots_needed free slots.
		# If the queue is full, check the timestamp of the earliest in-flight HTLC.
		# If it is in the past, pop the HTLC (so it can be resolved).
		# Return True / False and the released HTLC, if any, with its timestamp.
		success, htlcs = False, []
		num_free_slots = self.get_num_slots_free()
		if num_free_slots >= num_slots_needed:
			# we have enough free slots without needing to release any HTLCs
			success = True
		else:
			num_htlcs_to_release = num_slots_needed - num_free_slots
			for _ in range(num_htlcs_to_release):
				# Non-strict inequlity: we do resolve HTLCs that expire exactly now
				if self.get_top_timestamp() <= time:
					# free a slot by popping an outdated HTLC
					htlcs.append(self.pop_htlc())
					success = True
				else:
					# no more outdated HTLCs
					success = False
			if not success:
				# push back the released HTLCs if we couldn't pop enough of them
				for resolution_time, htlc in htlcs:
					self.push_htlc(resolution_time, htlc)
				htlcs = []
		return success, htlcs

	def ensure_free_slot(self, time):
		return self.ensure_free_slots(time, num_slots_needed=1)

	def set_deliberate_failure_behavior(self, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		self.deliberately_fail_prob = prob
		self.spoofing_error_type = spoofing_error_type

	def __repr__(self):  # pragma: no cover
		s = "\nChannelInDirection with properties:"
		s += "\nslots (busy / total):	" + str(self.get_num_slots_occupied())
		s += " / " + str(self.get_num_slots())
		s += "\nslots full?	" + str(self.all_slots_busy())
		return s

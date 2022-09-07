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
		spoofing_error_type=ErrorType.FAILED_DELIBERATELY,
		enabled=True):
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
				The probability with which this ch_dir deliberately fails payments
				(before making any other checks, like balance or slot checks).

			- spoofing_error_type
				The error type to return when deliberately failing a payment.

			- enabled
				True if this ch_dir forwards payments, False if not.
		'''
		# FIXME: get rid of enabled
		self.enabled = enabled
		self.set_fee(FeeType.UPFRONT, upfront_base_fee, upfront_fee_rate)
		self.set_fee(FeeType.SUCCESS, success_base_fee, success_fee_rate)
		# we remember num_slots in a separate variable:
		# there is no way to get maxsize from a queue after it's created
		self.max_num_slots = num_slots
		self.slots = PriorityQueue(maxsize=self.max_num_slots)
		self.deliberately_fail_prob = deliberately_fail_prob
		self.spoofing_error_type = spoofing_error_type

	def set_fee(self, fee_type, base_fee, fee_rate):
		assert(fee_type in (FeeType.UPFRONT, FeeType.SUCCESS))
		fee_function = partial(lambda a: generic_fee_function(base_fee, fee_rate, a))
		if fee_type == FeeType.UPFRONT:
			self.upfront_base_fee = base_fee
			self.upfront_fee_rate = fee_rate
			self.upfront_fee_function = fee_function
		elif fee_type == FeeType.SUCCESS:
			self.success_base_fee = base_fee
			self.success_fee_rate = fee_rate
			self.success_fee_function = fee_function

	def reset_with_num_slots(self, num_slots):
		# Initialize slots to a PriorityQueue of a given maxsize.
		# (An existing queue cannot be re-sized.)
		# Optionally, copy over all HTLCs from the old queue.
		# TODO: check that the new queue is larger than the old one if copy_existing_htlcs.
		self.max_num_slots = num_slots
		self.reset()

	def reset(self):
		self.slots = PriorityQueue(maxsize=self.max_num_slots)

	def is_enabled(self):
		return self.enabled

	def is_full(self):
		return self.slots.full()

	def is_empty(self):
		return self.slots.empty()

	def is_jammed(self, time):
		return not self.is_enabled() or self.is_full() and self.slots.queue[0][0] > time

	def get_max_num_slots(self):
		return self.max_num_slots

	def get_num_slots_occupied(self):
		# Note: this doesn't reflect that some slots may be occupied by outdated HTLCs!
		return self.slots.qsize()

	def get_top_timestamp(self):
		return self.slots.queue[0][0] if not self.is_empty() else None

	def get_total_fee(self, amount):
		success_fee = self.success_fee_function(amount)
		upfront_fee = self.upfront_fee_function(amount + success_fee)
		return success_fee + upfront_fee

	def ensure_free_slot(self, time, num_slots_needed=1):
		# Ensure there is a free slot.
		# If the queue is full, check the timestamp of the earliest in-flight HTLC.
		# If it is in the past, pop the HTLC (so it can be resolved).
		# Return True / False and the released HTLC, if any, with its timestamp.
		success, released_htlcs = False, []
		num_free_slots = self.max_num_slots - self.slots.qsize()
		if num_free_slots >= num_slots_needed:
			# we have enough free slots without the need to pop anything
			success = True
		else:
			num_slots_to_release = num_slots_needed - num_free_slots
			for _ in range(num_slots_to_release):
				earliest_in_flight_timestamp = self.slots.queue[0][0]
				# Non-strict: we do resolve HTLCs that expire exactly now
				if earliest_in_flight_timestamp <= time:
					resolution_time, released_htlc = self.slots.get_nowait()
					released_htlcs.append((resolution_time, released_htlc))
					# freed a slot by popping an outdated HTLC
					success = True
				else:
					# all slots full; no outdated HTLCs
					success = False
			if not success:
				for resolution_time, released_htlc in released_htlcs:
					self.store_htlc(resolution_time, released_htlc)
				released_htlcs = []
		return success, released_htlcs

	def store_htlc(self, resolution_time, in_flight_htlc):
		# Store an in-flight HTLC in the slots queue.
		# The queue must not be full!
		# (We must have called ensure_free_slot() earlier.)
		assert(not self.is_full())
		self.slots.put_nowait((resolution_time, in_flight_htlc))

	def get_htlc(self):
		assert(not self.is_empty())
		resolution_time, released_htlc = self.slots.get_nowait()
		return resolution_time, released_htlc

	def set_deliberate_failure_behavior(self, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		self.deliberately_fail_prob = prob
		self.spoofing_error_type = spoofing_error_type

	def __repr__(self):  # pragma: no cover
		s = "\nChannelInDirection with properties:"
		s += "\nis enabled:	" + str(self.is_enabled())
		s += "\nbusy slots:	" + str(self.get_num_slots_occupied())
		s += "\nmax slots:	" + str(self.get_max_num_slots())
		s += "\nslots full?	" + str(self.is_full())
		return s

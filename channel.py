from queue import PriorityQueue
from enum import Enum
from functools import partial

from params import generic_fee_function

import logging
logger = logging.getLogger(__name__)

# There are two channel directions encoded with a boolean value.
# Direction "dir0" (True) goes from smaller node ID to larger (alphanumerically).
# Direction "dir1" (False) is the opposite.
# The notation is arbitrary but it must be consistent.
# We set global variables dir0 and dir1 for readability.
dir0 = True
dir1 = False


class ErrorType(Enum):
	LOW_BALANCE = "no_balance"
	NO_SLOTS = "no_slots"
	FAILED_DELIBERATELY = "failed_deliberately"


class FeeType(Enum):
	UPFRONT = "upfront"
	SUCCESS = "success"


class ChannelDirection:
	'''
		A ChannelDirection models a Channel's forwarding process in one direction.
	'''

	def __init__(
		self,
		is_enabled,
		num_slots,
		upfront_base_fee,
		upfront_fee_rate,
		success_base_fee,
		success_fee_rate,
		deliberately_fail_prob=0,
		spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		'''
			- is_enabled
				True if this ch_dir forwards payments, False if not.

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
		'''
		self.is_enabled = is_enabled
		self.set_fee(FeeType.UPFRONT, upfront_base_fee, upfront_fee_rate)
		self.set_fee(FeeType.SUCCESS, success_base_fee, success_fee_rate)
		# we remember num_slots in a separate variable:
		# there is no way to get maxsize from a queue after it's created
		self.max_num_slots = num_slots
		self.slots = PriorityQueue(maxsize=self.max_num_slots)
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
		else:
			logger.error(f"Unexpected fee type {fee_type}! Can't set fee.")
			pass

	def set_num_slots(self, num_slots, copy_existing_htlcs=False):
		# Initialize slots to a PriorityQueue of a given maxsize.
		# (An existing queue cannot be re-sized.)
		# Optionally, copy over all HTLCs from the old queue.
		# TODO: check that the new queue is larger than the old one if copy_existing_htlcs.
		old_slots = self.slots
		self.max_num_slots = num_slots
		self.slots = PriorityQueue(maxsize=num_slots)
		if copy_existing_htlcs:
			if old_slots.qsize() > num_slots:
				logger.error(f"Can't copy {old_slots.qsize()} HTLCs into queue of size {num_slots}!")
				pass
			else:
				while not old_slots.empty():
					resolution_time, released_htlc = self.slots.get_nowait()
					self.slots.put_nowait((resolution_time, released_htlc))

	def is_jammed(self, current_timestamp):
		return not self.is_enabled or self.slots.full() and self.slots.queue[0][0] > current_timestamp

	def num_slots_occupied(self):
		# Note: this doesn't reflect that some slots may be occupied by outdated HTLCs!
		return self.slots.qsize()

	def top_timestamp(self):
		return self.slots.queue[0][0] if not self.slots.empty() else None

	def ensure_free_slot(self, current_timestamp, num_slots_needed=1):
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
				if earliest_in_flight_timestamp <= current_timestamp:
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
		return success, released_htlcs

	def store_htlc(self, resolution_time, in_flight_htlc):
		# Store an in-flight HTLC in the slots queue.
		# The queue must not be full!
		# (We must have called ensure_free_slot() earlier.)
		if self.slots.full():
			logger.error(f"Can't push HTLC {in_flight_htlc}: slots full!")
			assert(not self.slots.full())
		self.slots.put_nowait((resolution_time, in_flight_htlc))

	def __repr__(self):
		s = "\nChannelDirection with properties:"
		s += "\nis enabled:	" + str(self.is_enabled)
		s += "\nbusy slots:	" + str(self.slots.qsize())
		s += "\nmax slots:	" + str(self.slots.maxsize)
		s += "\nslots full?	" + str(self.slots.full())
		return s

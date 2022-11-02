from queue import PriorityQueue
from functools import partial

from enumtypes import ErrorType, FeeType

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
				The max size of the in-flight HTLC priority queue.
				The priority metric is HTLC resolution time.

			- upfront_base_fee
				A base fee for upfront fee function (satoshis).

			- upfront_fee_rate
				A rate for upfront fee function (proportion).

			- success_base_fee
				A base fee for success-case fee function (satoshis).

			- success_fee_rate
				A rate for upfront fee function (proportion).

			- deliberately_fail_prob
				The probability with which this ch_in_dir deliberately fails payments
				(before making any other checks, like balance or slot checks).
				Note: not used in actual simulations.

			- spoofing_error_type
				The error type to return when deliberately failing a payment.
				Note: not used in actual simulations.
		'''
		self.set_fee(FeeType.UPFRONT, upfront_base_fee, upfront_fee_rate)
		self.set_fee(FeeType.SUCCESS, success_base_fee, success_fee_rate)
		self.reset_slots(num_slots)
		self.deliberately_fail_prob = deliberately_fail_prob
		self.spoofing_error_type = spoofing_error_type

	@staticmethod
	def generic_fee_function(base, rate, amount):
		# A generic form of the fee includes a constant base fee and a proportional component.
		# Note: amount here refers either to payment _body_ (for success-case fee) or _amount_ (for unconditional / upfront fees).
		return base + rate * amount

	def set_fee(self, fee_type, base_fee, fee_rate):
		# Set a fee to a channel direction.
		# Note: we store both the fee coefficients and the fee function.
		# The fee function is the generic fee function partially applied (coefficients are given, the amount is not).
		fee_function = partial(lambda a: ChannelInDirection.generic_fee_function(base_fee, fee_rate, a))
		if fee_type == FeeType.UPFRONT:
			self.upfront_base_fee = base_fee
			self.upfront_fee_rate = fee_rate
			self.upfront_fee_function = fee_function
		elif fee_type == FeeType.SUCCESS:
			self.success_base_fee = base_fee
			self.success_fee_rate = fee_rate
			self.success_fee_function = fee_function

	def reset_slots(self, num_slots=None):
		# Initialize an HTLC priority queue of a given maximum size.
		# Note: an existing queue cannot be re-sized.
		# We store num_slots in a separate variable: we can't get it from a queue after it's created.
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
		# A channel direction is jammed at a given time if:
		# a) all slots are busy, and b) the earliest HTLC can't yet be resolved.
		return self.all_slots_busy() and self.get_earliest_htlc_resolution_time() > time

	def get_num_slots(self):
		# Get the maximum number of HTLCs the channel direction can keep in-flight.
		return self.num_slots

	def get_num_slots_occupied(self):
		# Get the number of HTLCs currently in the queue.
		# Note: some HTLCs may be outdated!
		return self.slots.qsize()

	def get_num_slots_free(self):
		# Get the number of slots that are free.
		# Note: we may free up additional slots if some HTLCs are outdated.
		return self.get_num_slots() - self.get_num_slots_occupied()

	def get_earliest_htlc_resolution_time(self):
		# Get the resolution time of the earliest HTLC in the queue without popping it.
		assert not self.all_slots_free()
		return self.slots.queue[0][0]

	def requires_fee_for_body(self, fee_type, body, zero_success_fee=False):
		# Calculate the fee of fee_type needed for the given payment body.
		# Note: upfront fee depends on amount, where amount = body + success_fee.
		# Success fee depends on body.
		success_fee = 0 if zero_success_fee else self.success_fee_function(body)
		if fee_type == FeeType.UPFRONT:
			amount = body + success_fee
			return self.upfront_fee_function(amount)
		elif fee_type == FeeType.SUCCESS:
			return success_fee

	def requires_fee(self, fee_type, payment, zero_success_fee=False):
		# Calculate the fee of fee_type required for the payment.
		# Last hop in route charges zero success fee by definition: next node does not have to forward anything.
		# Upfront fee, however, is still being paid, even on the last hop!
		# (It may have been subtracted from the amount at payment creation.)
		return self.requires_fee_for_body(fee_type, payment.get_body(), zero_success_fee)

	def enough_fee(self, payment, zero_success_fee=False):
		# Return True if the payment pays sufficient fee for this channel direction.
		enough_success_fee = payment.pays_fee(FeeType.SUCCESS) >= self.requires_fee(FeeType.SUCCESS, payment, zero_success_fee)
		enough_upfront_fee = payment.pays_fee(FeeType.UPFRONT) >= self.requires_fee(FeeType.UPFRONT, payment, zero_success_fee)
		return enough_success_fee and enough_upfront_fee

	def pop_htlc(self):
		# Pop the earliest HTLC from the queue along with its resolution timestamp.
		assert not self.all_slots_free()
		resolution_time, htlc = self.slots.get_nowait()
		return resolution_time, htlc

	def push_htlc(self, resolution_time, in_flight_htlc):
		# Store an HTLC in the slots queue with a given resolution time.
		# Note: the queue must not be full: we must have ensured this earlier.
		# See ensure_free_slots.
		assert not self.all_slots_busy()
		self.slots.put_nowait((resolution_time, in_flight_htlc))

	def ensure_free_slots(self, time, num_slots_needed=1):
		# Ensure there are num_slots_needed free slots in the HTLC queue.
		# If the queue is full, check the timestamp of the earliest in-flight HTLC.
		# If it is in the past, pop that HTLC (so it can be resolved).
		# Repeat until enough slots are freed up, or until the next earliest HTLC isn't outdated.
		# In the former case, re-insert the popped HTLCs back into the queue.
		# Return success (True / False) and the released HTLCs, if any, along with their timestamps.
		success, released_htlcs = False, []
		num_free_slots = self.get_num_slots_free()
		if num_free_slots >= num_slots_needed:
			# we have enough free slots without popping outdated HTLCs
			success = True
		else:
			num_htlcs_to_release = num_slots_needed - num_free_slots
			for _ in range(num_htlcs_to_release):
				# non-strict inequality: we _resolve_ HTLCs that expire exactly now
				if self.get_earliest_htlc_resolution_time() <= time:
					# free a slot by popping an outdated HTLC
					released_htlcs.append(self.pop_htlc())
					success = True
				else:
					# there are no more outdated HTLCs
					success = False
			if not success:
				# push back the released HTLCs if we couldn't pop enough of them
				for resolution_time, htlc in released_htlcs:
					self.push_htlc(resolution_time, htlc)
				released_htlcs = []
		return success, released_htlcs

	def set_deliberate_failure_behavior(self, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		# Set the spoofed error type and the probability of deliberate failure.
		# Note: this isn't used in the simulations.
		self.deliberately_fail_prob = prob
		self.spoofing_error_type = spoofing_error_type

	def __repr__(self):  # pragma: no cover
		s = "\nChannelInDirection with properties:"
		s += "\nslots (busy / total):	" + str(self.get_num_slots_occupied())
		s += " / " + str(self.get_num_slots())
		s += "\nslots full?	" + str(self.all_slots_busy())
		return s

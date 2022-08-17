from queue import PriorityQueue
from enum import Enum

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


class ChannelDirection:
	'''
		A ChannelDirection models a Channel's forwarding process in one direction.
	'''

	def __init__(
		self,
		is_enabled,
		num_slots,
		upfront_fee_function,
		success_fee_function,
		deliberately_fail_prob=0,
		spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		'''
			- is_enabled
				True if this ch_dir forwards payments, False if not.

			- slots
				A PriorityQueue of in-flight HTLCs.
				The queue priority metric is HTLC resolution time.

			- upfront_fee_function
				A function defining the upfront fee for this ch_dir.

			- success_fee_function
				A function defining the success-case fee for this ch_dir.

			- deliberately_fail_prob
				The probability with which this ch_dir deliberately fails payments
				(before making any other checks, like balance or slot checks).

			- spoofing_error_type
				The error type to return when deliberately failing a payment.
		'''
		self.is_enabled = is_enabled
		self.upfront_fee_function = upfront_fee_function
		self.success_fee_function = success_fee_function
		self.slots = PriorityQueue(maxsize=num_slots)
		self.deliberately_fail_prob = deliberately_fail_prob
		self.spoofing_error_type = spoofing_error_type

	def set_num_slots(self, num_slots, copy_existing_htlcs=False):
		# Initialize slots to a PriorityQueue of a given maxsize.
		# (An existing queue cannot be re-sized.)
		# Optionally, copy over all HTLCs from the old queue.
		# TODO: check that the new queue is larger than the old one if copy_existing_htlcs.
		old_slots = self.slots
		self.slots = PriorityQueue(maxsize=num_slots)
		if copy_existing_htlcs:
			if old_slots.qsize() > num_slots:
				# print("Can't copy over in-flight HTLCs into a resized queue!")
				pass
			else:
				while not old_slots.empty():
					resolution_time, released_htlc = self.slots.get_nowait()
					self.slots.put_nowait((resolution_time, released_htlc))

	def ensure_free_slot(self, current_timestamp):
		# Ensure there is a free slot.
		# If the queue is full, check the timestamp of the earliest in-flight HTLC.
		# If it is in the past, pop the HTLC (so it can be resolved).
		# Return True / False and the released HTLC, if any, with its timestamp.
		success, resolution_time, released_htlc = False, None, None
		if self.slots.full():
			earliest_in_flight_timestamp = self.slots.queue[0][0]
			# Non-strict: we do resolve HTLCs that expire exactly now
			if earliest_in_flight_timestamp <= current_timestamp:
				resolution_time, released_htlc = self.slots.get_nowait()
				# freed a slot by popping an outdated HTLC
				success = True
			else:
				# all slots full; no outdated HTLCs
				success = False
		else:
			# got a free slot without popping any older HTLC
			success = True
		return success, resolution_time, released_htlc

	def store_htlc(self, resolution_time, in_flight_htlc):
		# Store an in-flight HTLC in the slots queue.
		# The queue must not be full!
		# (We must have called ensure_free_slot() earlier.)
		assert(not self.slots.full())
		self.slots.put_nowait((resolution_time, in_flight_htlc))

	def __repr__(self):
		s = "\nChannelDirection with properties:"
		s += "\nis enabled:	" + str(self.is_enabled)
		s += "\nbusy slots:	" + str(self.slots.qsize())
		s += "\nmax slots:	" + str(self.slots.maxsize)
		s += "\nslots full?	" + str(self.slots.full())
		return s

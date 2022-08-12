from queue import PriorityQueue

# There are two channel directions encoded with a boolean value.
# Direction "dir0" (True) goes from smaller node ID to larger (alphanumerically).
# Direction "dir1" (False) is the opposite.
# The notation is arbitrary but it must be consistent.
# We set global variables dir0 and dir1 for readability.
dir0 = True
dir1 = False

class ChannelDirection:
	'''
		A ChannelDirection model Channel's forwarding process in one direction.
		A ChannelDirection contains:
		- slots: a list of htlcs (or None) of form:
			(timestamp, in-flight-fee, actual_success)
			Timestamp is when in-flight fee must move to one of the parties
			depending on actual_success.
			slots == None means the direction is disabled.
			slots == [None, ..., None] means there are N free slots.
		- success-case fee function
		- upfront fee function
	'''
	def __init__(self,
		is_enabled,
		num_slots,
		upfront_fee_function,
		success_fee_function):
		self.is_enabled = is_enabled
		self.upfront_fee_function = upfront_fee_function
		self.success_fee_function = success_fee_function
		self.slots = PriorityQueue(maxsize=num_slots)

	def set_num_slots(self, num_slots, copy_existing_htlcs=False):
		old_slots = self.slots
		self.slots = PriorityQueue(maxsize=num_slots)
		if copy_existing_htlcs:
			while not old_slots.empty():
				resolution_time, released_htlc = self.slots.get_nowait()
				self.slots.put_nowait((resolution_time, released_htlc))

	def ensure_free_slot(self, current_timestamp):
		# If slots are full, try to pop the earliest one.
		# If the earliest one is after now, release it.
		# Return success True / False and released htlc, if any.
		# The htlc is to be handled by the caller
		# (i.e., add revenue to nodes; Channel doesn't know about Nodes).
		success, resolution_time, released_htlc = False, None, None
		if self.slots.full():
			earliest_in_flight_timestamp = self.slots.queue[0][0]
			if earliest_in_flight_timestamp <= current_timestamp:
				resolution_time, released_htlc = self.slots.get_nowait()
				success = True
			else:
				# no slots, and too early to release even the earliest htlc
				success = False
		else:
			success = True
		return success, resolution_time, released_htlc

	def store_htlc(self, resolution_time, in_flight_htlc):
		# Occupy a slot. We must have called ensure_free_slot() earlier.
		assert(not self.slots.full())
		self.slots.put_nowait((resolution_time, in_flight_htlc))

	def __repr__(self):
		s = "\nChannelDirection with properties:"
		s += "\nis enabled:	" + str(self.is_enabled)
		s += "\nbusy slots:	" + str(self.slots.qsize())
		s += "\nmax slots:	" + str(self.slots.maxsize)
		return s


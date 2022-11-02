from direction import Direction
from channelindirection import ChannelInDirection
from enumtypes import ErrorType
from utils import generate_id

import logging
logger = logging.getLogger(__name__)


class Channel:
	'''
		A channel between two nodes.
	'''

	def __init__(self, capacity, cid=None, num_slots_per_direction=None):
		'''
			- capacity
				The channel capacity in satoshis.

			- cid
				The channel identifier.

			- num_slots_per_direction
				The size of the HTLC queue (i.e., the number of slots) for each direction.
		'''
		cid = cid if cid is not None else generate_id()
		self.cid = cid
		self.set_capacity(capacity)
		self.channel_in_direction = {Direction.Alph: None, Direction.NonAlph: None}
		# if the number of slots is given, initialize both channel directions with that number of slots
		if num_slots_per_direction is not None:
			for direction in (Direction.Alph, Direction.NonAlph):
				self.enable_direction_with_num_slots(direction, num_slots_per_direction)

	def get_cid(self):
		return self.cid

	def get_capacity(self):
		return self.capacity

	def set_capacity(self, capacity):
		# Modify the routing graph in the LNModel accordingly!
		self.capacity = capacity

	def in_direction(self, direction):
		return self.channel_in_direction[direction]

	def is_enabled_in_direction(self, direction):
		return self.in_direction(direction) is not None

	def maybe_can_forward_in_direction(self, direction, amount):
		# A channel can forward if it is enabled and has sufficient capacity.
		# It also must not be jammed, but this varies through time.
		# See really_can_forward_in_direction_at_time
		return (
			self.is_enabled_in_direction(direction)
			and amount <= self.capacity)

	def really_can_forward_in_direction_at_time(self, direction, time, amount):
		# A channel definitely can forward, if it has the capacity, is enabled, and isn't jammed.
		# Note: whether the channel is jammed or not, changes with (simulated) time.
		# Note: payments still fail with probability = amount / capacity.
		return (
			self.maybe_can_forward_in_direction(direction, amount)
			and not self.in_direction(direction).is_jammed(time))

	def get_num_slots_occupied_in_direction(self, direction):
		# Get the number of busy slots.
		# Note: this may include HTLCs with resolution timestamps in the past.
		# These are resolved lazily or at the end of simulation.
		if not self.is_enabled_in_direction(direction):
			return 0
		return self.in_direction(direction).get_num_slots_occupied()

	def enable_direction_with_num_slots(self, direction, num_slots):
		# Reset the channel direction with a given maximum number of slots.
		assert not self.is_enabled_in_direction(direction)
		self.channel_in_direction[direction] = ChannelInDirection(num_slots)

	def set_fee_in_direction(self, direction, fee_type, base_fee, fee_rate):
		# Set the fee coefficients for a given direction.
		# Note: the channel must be enabled for its fee to be set.
		assert self.is_enabled_in_direction(direction)
		self.in_direction(direction).set_fee(fee_type, base_fee, fee_rate)

	def set_deliberate_failure_behavior_in_direction(self, direction, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		# Set the spoofed error type for deliberately failed payments.
		# Note: this hasn't been fully implemented.
		assert self.is_enabled_in_direction(direction)
		self.in_direction(direction).set_deliberate_failure_behavior(prob, spoofing_error_type)

	def reset_slots_in_direction(self, direction, num_slots):
		# Re-initialize a channel direction with a given number of slots.
		# Note: previously stored HTLCs will be lost.
		if self.is_enabled_in_direction(direction):
			self.in_direction(direction).reset_slots(num_slots)

	def __repr__(self):  # pragma: no cover
		s = "\nChannel with properties:"
		s += "\ncapacity:	" + str(self.capacity)
		for direction in (Direction.Alph, Direction.NonAlph):
			s += "\nin direction " + str(direction) + ": " + str(self.in_direction(direction))
		return s

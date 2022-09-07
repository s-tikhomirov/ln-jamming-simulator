from direction import Direction
from channelindirection import ChannelInDirection
from enumtypes import ErrorType

import logging
logger = logging.getLogger(__name__)


class Channel:

	def __init__(self, capacity, num_slots_per_direction=None):
		self.capacity = capacity
		self.in_direction = {Direction.Alph: None, Direction.NonAlph: None}
		if num_slots_per_direction is not None:
			self.enable_direction_with_num_slots(Direction.Alph, num_slots_per_direction)
			self.enable_direction_with_num_slots(Direction.NonAlph, num_slots_per_direction)

	def get_channel_in_direction(self, direction):
		return self.in_direction[direction]

	def is_enabled_in_direction(self, direction):
		return self.get_channel_in_direction(direction) is not None

	def is_jammed_in_direction_at_time(self, direction, time):
		assert self.is_enabled_in_direction(direction)
		return self.get_channel_in_direction(direction).is_jammed(time)

	def is_available_in_direction_at_time(self, direction, time):
		return self.is_enabled_in_direction(direction) and not self.is_jammed_in_direction_at_time(direction, time)

	def get_num_slots_occupied_in_direction(self, direction):
		if not self.is_enabled_in_direction(direction):
			return 0
		return self.get_channel_in_direction(direction).get_num_slots_occupied()

	def enable_direction_with_num_slots(self, direction, num_slots):
		assert not self.is_enabled_in_direction(direction)
		self.in_direction[direction] = ChannelInDirection(num_slots)

	def set_fee_in_direction(self, direction, fee_type, base_fee, fee_rate):
		# don't allow setting fee for a disabled channel direction
		assert self.is_enabled_in_direction(direction)
		self.get_channel_in_direction(direction).set_fee(fee_type, base_fee, fee_rate)

	def can_forward_in_direction(self, direction, amount):
		return self.is_enabled_in_direction(direction) and amount <= self.capacity

	def get_total_fee_in_direction(self, direction, amount):
		assert self.is_enabled_in_direction(direction)
		return self.get_channel_in_direction(direction).get_total_fee(amount)

	def set_deliberate_failure_behavior_in_direction(self, direction, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		assert self.is_enabled_in_direction(direction)
		self.get_channel_in_direction(direction).set_deliberate_failure_behavior(prob, spoofing_error_type)

	def __repr__(self):  # pragma: no cover
		s = "\nChannel with properties:"
		s += "\ncapacity:	" + str(self.capacity)
		for direction in (Direction.Alph, Direction.NonAlph):
			s += "\nin direction " + str(direction) + ": " + str(self.get_channel_in_direction(direction))
		return s

from channelindirection import ChannelInDirection
from enumtypes import ErrorType
from direction import Direction

import logging
logger = logging.getLogger(__name__)


class Channel:

	def __init__(self, capacity, num_slots_per_direction=None):
		self.capacity = capacity
		self.in_direction = {Direction.Alph: None, Direction.NonAlph: None}
		if num_slots_per_direction is not None:
			self.add_ch_in_dir_with_num_slots(num_slots_per_direction)

	def add_ch_in_dir_with_num_slots(self, num_slots):
		ch_in_dir_alph = ChannelInDirection(num_slots)
		ch_in_dir_nonalph = ChannelInDirection(num_slots)
		self.add_ch_in_dir(ch_in_dir_alph, Direction.Alph)
		self.add_ch_in_dir(ch_in_dir_nonalph, Direction.NonAlph)

	def is_enabled_in_direction(self, direction):
		return self.in_direction[direction] is not None

	def is_enabled_in_both_directions(self):
		return (
			self.is_enabled_in_direction(Direction.Alph)
			and self.is_enabled_in_direction(Direction.NonAlph))

	def is_jammed(self, direction, time):
		# FIXME: is a non-existent ch_in_dir jammed?
		if self.in_direction[direction] is None:
			return True
		return self.in_direction[direction].is_jammed(time)

	def get_num_slots_occupied(self, direction):
		if self.in_direction[direction] is None:
			return 0
		return self.in_direction[direction].get_num_slots_occupied()

	def add_ch_in_dir(self, ch_in_dir, direction):
		assert(self.in_direction[direction] is None)
		self.in_direction[direction] = ch_in_dir

	def get_ch_in_dir(self, direction):
		return self.in_direction[direction]

	def set_fee_in_direction(self, fee_type, base_fee, fee_rate, direction):
		# don't allow setting fee for a disabled channel direction
		assert(self.is_enabled_in_direction(direction))
		self.in_direction[direction].set_fee(fee_type, base_fee, fee_rate)

	def can_forward(self, amount, direction):
		return self.is_enabled_in_direction(direction) and amount <= self.capacity

	def get_total_fee_in_direction(self, amount, direction):
		assert(self.can_forward(amount, direction))
		ch_in_dir = self.in_direction[direction]
		return ch_in_dir.get_total_fee(amount)

	def set_deliberate_failure_behavior_in_direction(self, direction, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		ch_in_dir = self.in_direction[direction]
		if ch_in_dir is not None:
			ch_in_dir.set_deliberate_failure_behavior(prob, spoofing_error_type)

	def __repr__(self):  # pragma: no cover
		s = "\nChannel with properties:"
		s += "\ncapacity:	" + str(self.capacity)
		s += "\nch_in_dirs:	" + str(self.in_direction)
		return s

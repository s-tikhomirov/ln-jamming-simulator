from channelindirection import ChannelInDirection
from enumtypes import ErrorType
from direction import Direction

import logging
logger = logging.getLogger(__name__)


class Channel:

	def __init__(self, capacity, num_slots_per_direction=None):
		self.capacity = capacity
		self.directions = {Direction.Alph: None, Direction.NonAlph: None}
		if num_slots_per_direction is not None:
			self.add_chdir_with_num_slots(num_slots_per_direction)

	def add_chdir_with_num_slots(self, num_slots):
		chdir_0 = ChannelInDirection(num_slots)
		chdir_1 = ChannelInDirection(num_slots)
		self.add_chdir(chdir_0, Direction.Alph)
		self.add_chdir(chdir_1, Direction.NonAlph)

	def is_enabled_in_direction(self, direction):
		if self.directions[direction] is None:
			logger.debug(f"Direction {direction} is None")
			return False
		else:
			return self.directions[direction].is_enabled()

	def is_enabled_in_both_directions(self):
		return (
			self.is_enabled_in_direction(Direction.Alph)
			and self.is_enabled_in_direction(Direction.NonAlph))

	def is_jammed(self, direction, time):
		# FIXME: is a non-existent ch_dir jammed?
		if self.directions[direction] is None:
			return True
		return self.directions[direction].is_jammed(time)

	def get_num_slots_occupied(self, direction):
		if self.directions[direction] is None:
			return 0
		return self.directions[direction].get_num_slots_occupied()

	def add_chdir(self, chdir, direction):
		assert(self.directions[direction] is None)
		self.directions[direction] = chdir

	def get_chdir(self, direction):
		return self.directions[direction]

	def set_fee_in_direction(self, fee_type, base_fee, fee_rate, direction):
		# don't allow setting fee for a disabled channel direction
		assert(self.is_enabled_in_direction(direction))
		self.directions[direction].set_fee(fee_type, base_fee, fee_rate)

	def can_forward(self, amount, direction):
		if not self.is_enabled_in_direction(direction):
			return False
		return amount <= self.capacity

	def get_total_fee_in_direction(self, amount, direction):
		assert(self.can_forward(amount, direction))
		chdir = self.directions[direction]
		return chdir.get_total_fee(amount)

	def reset_in_flight_htlcs(self):
		for direction in (Direction.Alph, Direction.NonAlph):
			if self.directions[direction] is not None:
				self.directions[direction].reset()

	def set_deliberate_failure_behavior_in_direction(self, direction, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		ch_dir = self.directions[direction]
		if ch_dir is not None:
			ch_dir.set_deliberate_failure_behavior(prob, spoofing_error_type)

	def __repr__(self):  # pragma: no cover
		s = "\nChannel with properties:"
		s += "\ncapacity:	" + str(self.capacity)
		s += "\nchdirs:	" + str(self.directions)
		return s

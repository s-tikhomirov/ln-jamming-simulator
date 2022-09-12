from direction import Direction
from channelindirection import ChannelInDirection
from enumtypes import ErrorType
from utils import generate_id

import logging
logger = logging.getLogger(__name__)


class Channel:

	def __init__(self, capacity, cid=None, num_slots_per_direction=None):
		cid = cid if cid is not None else generate_id()
		self.cid = cid
		self.set_capacity(capacity)
		self.channel_in_direction = {Direction.Alph: None, Direction.NonAlph: None}
		if num_slots_per_direction is not None:
			for direction in (Direction.Alph, Direction.NonAlph):
				self.enable_direction_with_num_slots(direction, num_slots_per_direction)

	def get_cid(self):
		return self.cid

	def get_capacity(self):
		return self.capacity

	def set_capacity(self, capacity):
		# modify the routing graph in the LNModel accordingly!
		self.capacity = capacity

	def in_direction(self, direction):
		return self.channel_in_direction[direction]

	def is_enabled_in_direction(self, direction):
		return self.in_direction(direction) is not None

	def maybe_can_forward_in_direction_at_time(self, direction, amount):
		return (
			self.is_enabled_in_direction(direction)
			and amount <= self.capacity)

	def really_can_forward_in_direction_at_time(self, direction, time, amount):
		return (
			self.maybe_can_forward_in_direction_at_time(direction, amount)
			and not self.in_direction(direction).is_jammed(time))

	def get_num_slots_occupied_in_direction(self, direction):
		if not self.is_enabled_in_direction(direction):
			return 0
		return self.in_direction(direction).get_num_slots_occupied()

	def enable_direction_with_num_slots(self, direction, num_slots):
		assert not self.is_enabled_in_direction(direction)
		self.channel_in_direction[direction] = ChannelInDirection(num_slots)

	def set_fee_in_direction(self, direction, fee_type, base_fee, fee_rate):
		# don't allow setting fee for a disabled channel direction
		assert self.is_enabled_in_direction(direction)
		self.in_direction(direction).set_fee(fee_type, base_fee, fee_rate)

	def get_total_fee_in_direction(self, direction, amount):
		assert self.is_enabled_in_direction(direction)
		return self.in_direction(direction).requires_total_fee(amount)

	def set_deliberate_failure_behavior_in_direction(self, direction, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		assert self.is_enabled_in_direction(direction)
		self.in_direction(direction).set_deliberate_failure_behavior(prob, spoofing_error_type)

	def reset_slots_in_direction(self, direction, num_slots):
		if self.is_enabled_in_direction(direction):
			self.in_direction(direction).reset_slots(num_slots)

	def __repr__(self):  # pragma: no cover
		s = "\nChannel with properties:"
		s += "\ncapacity:	" + str(self.capacity)
		for direction in (Direction.Alph, Direction.NonAlph):
			s += "\nin direction " + str(direction) + ": " + str(self.in_direction(direction))
		return s

from chdir import ErrorType
from utils import generate_id

import logging
logger = logging.getLogger(__name__)


class Hop:

	def __init__(self):
		self.channels = {}

	def add_channel(self, channel, cid):
		cid = cid if cid is not None else generate_id()
		assert(cid not in self.channels)
		self.channels[cid] = channel

	def get_channel(self, cid):
		if cid not in self.channels:
			return None
		return self.channels[cid]

	def get_cids(self):
		return list(self.channels.keys())

	def get_channels(self):
		return list(self.channels.values())

	def get_num_cids(self):
		return len(self.channels)

	def get_cids_enabled_in_direction(self, direction):
		return [cid for cid in self.channels if self.channels[cid].is_enabled_in_direction(direction)]

	def get_cids_can_forward(self, amount, direction):
		return [cid for cid in self.get_cids_enabled_in_direction(direction) if self.channels[cid].can_forward(amount, direction)]

	def get_cids_can_forward_by_fee(self, amount, direction):
		return sorted(
			self.get_cids_can_forward(amount, direction),
			key=lambda cid: self.channels[cid].get_total_fee_in_direction(amount, direction))

	def get_cheapest_cid(self, amount, direction):
		cids_sorted = self.get_cids_can_forward_by_fee(amount, direction)
		return cids_sorted[0] if cids_sorted else None

	def has_cid(self, cid):
		return cid in self.channels

	def set_deliberate_failure_behavior_for_all_in_direction(self, direction, prob, spoofing_error_type=ErrorType.FAILED_DELIBERATELY):
		for cid, ch in self.channels.items():
			ch.set_deliberate_failure_behavior_in_direction(direction, prob, spoofing_error_type)

	def is_jammed(self, direction, time):
		return all(ch.is_jammed(direction, time) for ch in self.channels.values())

	def get_num_slots_occupied(self, direction):
		return sum(ch.get_num_slots_occupied(direction) for ch in self.channels.values())

	def get_jammed_status(self, direction, time):
		return (self.is_jammed(direction, time), self.get_num_slots_occupied(direction))

	def __repr__(self):  # pragma no cover
		s = "Hop with properties:"
		s += "Channels:	" + str(self.channels.items())
		return s

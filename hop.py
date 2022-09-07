from functools import partial

import logging
logger = logging.getLogger(__name__)


class Hop:

	def __init__(self):
		self.channels = {}

	def has_channel(self, cid):
		return cid in self.channels

	def add_channel(self, channel):
		cid = channel.get_cid()
		assert not self.has_channel(cid)
		self.channels[cid] = channel

	def get_num_channels(self):
		return len(self.channels)

	def get_channel(self, cid):
		if not self.has_channel(cid):
			return None
		return self.channels[cid]

	def get_all_channels(self):
		return self.channels.values()

	def get_channels_with_condition(self, condition=lambda ch: True, sorting_function=lambda ch: 0):
		return sorted([ch for ch in self.get_all_channels() if condition(ch)], key=sorting_function)

	def get_cheapest_channel_really_can_forward(self, direction, time, amount):
		# A channel REALLY can forward if it has enough capacity and is NOT JAMMED
		channels = self.get_channels_with_condition(
			condition=lambda ch: ch.really_can_forward_in_direction_at_time(direction, time, amount))
		return channels[0] if channels else None

	def get_cheapest_channel_maybe_can_forward(self, direction, amount):
		# A channel MAYBE can forward if it has enough capacity, but jamming status is not checked
		channels = self.get_channels_with_condition(
			condition=lambda ch: ch.maybe_can_forward_in_direction_at_time(direction, amount))
		return channels[0] if channels else None

	def really_can_forward_in_direction_at_time(self, direction, time, amount):
		return any(ch.really_can_forward_in_direction_at_time(direction, time, amount) for ch in self.get_all_channels())

	def can_forward(self, direction, time):
		# Can forward at least some amount (i.e., has a slot)
		return self.really_can_forward_in_direction_at_time(direction, time, amount=0)

	def cannot_forward(self, direction, time):
		# Cannot forward even zero amount (i.e., ANY amount)
		return not self.can_forward(direction, time)

	def get_total_num_slots_occupied_in_direction(self, direction):
		return sum(ch.get_num_slots_occupied_in_direction(direction) for ch in self.get_all_channels())

	def get_jammed_status(self, direction, time):
		return (self.cannot_forward(direction, time), self.get_total_num_slots_occupied_in_direction(direction))

	def __repr__(self):  # pragma no cover
		s = "Hop with properties:"
		s += "Channels:	" + str(self.channels.items())
		return s

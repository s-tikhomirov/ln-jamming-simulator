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
		# Return a list of channels that satisfy a condition, ordered with a sorting function.
		return sorted([ch for ch in self.get_all_channels() if condition(ch)], key=sorting_function)

	def get_cheapest_channel_really_can_forward(self, direction, time, amount):
		# Return the channel that can forward the amount, isn't jammed at the given time, and charges the lowest fee.
		channels = self.get_channels_with_condition(
			condition=lambda ch: ch.really_can_forward_in_direction_at_time(direction, time, amount))
		return channels[0] if channels else None

	def get_cheapest_channel_maybe_can_forward(self, direction, amount):
		# Return the channel that can forward the amount and charges the lowest fee.
		# Note: jamming status is not checked!
		channels = self.get_channels_with_condition(
			condition=lambda ch: ch.maybe_can_forward_in_direction(direction, amount))
		return channels[0] if channels else None

	def really_can_forward_in_direction_at_time(self, direction, time, amount):
		# Return True is _some_ channel can forward a given amount at a given time.
		return any(ch.really_can_forward_in_direction_at_time(direction, time, amount) for ch in self.get_all_channels())

	def can_forward(self, direction, time):
		# Return True if _some_ channel can forward _some_ amount at a given time.
		return self.really_can_forward_in_direction_at_time(direction, time, amount=0)

	def cannot_forward(self, direction, time):
		# Return True if no channel can forward any amount.
		return not self.can_forward(direction, time)

	def get_total_num_slots_occupied_in_direction(self, direction):
		# Return the total number of occupied slots in all channels of this hop in a given direction.
		return sum(ch.get_num_slots_occupied_in_direction(direction) for ch in self.get_all_channels())

	def get_jammed_status(self, direction, time):
		# Return jammed status (can / cannot forward anything) and the total number of occupied slots.
		# Note: useful for debugging jamming simulations.
		return (self.cannot_forward(direction, time), self.get_total_num_slots_occupied_in_direction(direction))

	def __repr__(self):  # pragma no cover
		s = "Hop with properties:"
		s += "Channels:	" + str(self.channels.items())
		return s

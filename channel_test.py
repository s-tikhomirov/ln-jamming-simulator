from channel import Channel
from direction import Direction

import logging
logger = logging.getLogger(__name__)


def test_channel_setup():
	ch = Channel(capacity=1000)
	assert(ch.capacity == 1000)
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	assert(ch.in_direction(Direction.Alph) is not None)
	assert(ch.is_enabled_in_direction(Direction.Alph))
	assert(ch.in_direction(Direction.NonAlph) is None)
	assert(not ch.is_enabled_in_direction(Direction.NonAlph))


def test_channel_can_forward():
	ch = Channel(capacity=1000)
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	assert(ch.really_can_forward_in_direction_at_time(Direction.Alph, time=0, amount=500))
	assert(not ch.really_can_forward_in_direction_at_time(Direction.NonAlph, time=0, amount=500))
	ch.enable_direction_with_num_slots(Direction.NonAlph, num_slots=2)
	assert(ch.really_can_forward_in_direction_at_time(Direction.NonAlph, time=0, amount=500))

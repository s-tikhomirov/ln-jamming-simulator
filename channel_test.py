from channel import Channel
from htlc import InFlightHtlc
from direction import Direction

import logging
logger = logging.getLogger(__name__)


def test_channel_setup():
	ch = Channel(capacity=1000)
	assert(ch.capacity == 1000)
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	assert(ch.get_channel_in_direction(Direction.Alph) is not None)
	assert(ch.is_enabled_in_direction(Direction.Alph))
	assert(ch.get_channel_in_direction(Direction.NonAlph) is None)
	assert(not ch.is_enabled_in_direction(Direction.NonAlph))


def test_channel_can_forward():
	ch = Channel(capacity=1000)
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	assert(ch.can_forward_in_direction(Direction.Alph, 500))
	assert(not ch.can_forward_in_direction(Direction.NonAlph, 500))
	ch.enable_direction_with_num_slots(Direction.NonAlph, num_slots=2)
	assert(ch.can_forward_in_direction(Direction.NonAlph, 500))


def test_channel_is_available():
	ch = Channel(capacity=1000)
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	assert(ch.is_available_in_direction_at_time(Direction.Alph, time=0))
	assert(not ch.is_available_in_direction_at_time(Direction.NonAlph, time=0))
	assert(ch.get_num_slots_occupied_in_direction(Direction.Alph) == 0)
	assert(ch.get_num_slots_occupied_in_direction(Direction.NonAlph) == 0)
	htlc = InFlightHtlc(payment_id="pid1", success_fee=0, desired_result=True)
	ch_in_dir_alph = ch.get_channel_in_direction(Direction.Alph)
	ch_in_dir_alph.store_htlc(resolution_time=1, in_flight_htlc=htlc)
	assert(ch.get_num_slots_occupied_in_direction(Direction.Alph) == 1)
	resolution_htlc, released_htlc = ch_in_dir_alph.get_htlc()
	assert(ch.get_num_slots_occupied_in_direction(Direction.Alph) == 0)

from channel import Channel
from channelindirection import ChannelInDirection
from htlc import InFlightHtlc
from direction import Direction

import logging
logger = logging.getLogger(__name__)


def test_channel_setup():
	ch = Channel(capacity=1000)
	assert(ch.capacity == 1000)
	ch_dir_0 = ChannelInDirection(num_slots=2)
	ch.add_chdir(ch_dir_0, Direction.Alph)
	assert(ch.get_chdir(Direction.Alph) is not None)
	assert(ch.is_enabled_in_direction(Direction.Alph))
	assert(ch.get_chdir(Direction.NonAlph) is None)
	assert(not ch.is_enabled_in_direction(Direction.NonAlph))


def test_channel_can_forward():
	ch = Channel(capacity=1000)
	ch_dir_0 = ChannelInDirection(num_slots=2)
	ch_dir_1 = ChannelInDirection(num_slots=2)
	ch.add_chdir(ch_dir_0, Direction.Alph)
	assert(ch.can_forward(500, Direction.Alph))
	assert(not ch.can_forward(500, Direction.NonAlph))
	ch.add_chdir(ch_dir_1, Direction.NonAlph)
	assert(ch.can_forward(500, Direction.NonAlph))


def test_channel_is_jammed():
	ch = Channel(capacity=1000)
	ch_dir_0 = ChannelInDirection(num_slots=2)
	ch.add_chdir(ch_dir_0, Direction.Alph)
	assert(ch.is_jammed(Direction.NonAlph, time=0))
	assert(not ch.is_jammed(Direction.Alph, time=0))
	assert(ch.get_num_slots_occupied(Direction.Alph) == 0)
	assert(ch.get_num_slots_occupied(Direction.NonAlph) == 0)
	htlc = InFlightHtlc(payment_id="pid1", success_fee=0, desired_result=True)
	ch_dir_0.store_htlc(resolution_time=1, in_flight_htlc=htlc)
	assert(ch.get_num_slots_occupied(Direction.Alph) == 1)
	resolution_htlc, released_htlc = ch_dir_0.get_htlc()
	assert(ch.get_num_slots_occupied(Direction.Alph) == 0)

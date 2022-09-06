from channel import Channel
from chdir import ChannelDirection, dir0, dir1
from htlc import InFlightHtlc

import logging
logger = logging.getLogger(__name__)


def test_channel_setup():
	ch = Channel(capacity=1000)
	assert(ch.capacity == 1000)
	ch_dir_0 = ChannelDirection(num_slots=2)
	ch.add_chdir(ch_dir_0, dir0)
	assert(ch.get_chdir(dir0) is not None)
	assert(ch.is_enabled_in_direction(dir0))
	assert(ch.get_chdir(dir1) is None)
	assert(not ch.is_enabled_in_direction(dir1))


def test_channel_can_forward():
	ch = Channel(capacity=1000)
	ch_dir_0 = ChannelDirection(num_slots=2)
	ch_dir_1 = ChannelDirection(num_slots=2)
	ch.add_chdir(ch_dir_0, dir0)
	assert(ch.can_forward(500, dir0))
	assert(not ch.can_forward(500, dir1))
	ch.add_chdir(ch_dir_1, dir1)
	assert(ch.can_forward(500, dir1))


def test_channel_is_jammed():
	ch = Channel(capacity=1000)
	ch_dir_0 = ChannelDirection(num_slots=2)
	ch.add_chdir(ch_dir_0, dir0)
	assert(ch.is_jammed(dir1, time=0))
	assert(not ch.is_jammed(dir0, time=0))
	assert(ch.get_num_slots_occupied(dir0) == 0)
	assert(ch.get_num_slots_occupied(dir1) == 0)
	htlc = InFlightHtlc(payment_id="pid1", success_fee=0, desired_result=True)
	ch_dir_0.store_htlc(resolution_time=1, in_flight_htlc=htlc)
	assert(ch.get_num_slots_occupied(dir0) == 1)
	resolution_htlc, released_htlc = ch_dir_0.get_htlc()
	assert(ch.get_num_slots_occupied(dir0) == 0)

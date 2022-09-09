from hop import Hop
from channel import Channel
from enumtypes import FeeType
from direction import Direction
from htlc import InFlightHtlc

import logging
logger = logging.getLogger(__name__)


def test_hop_create():
	hop = Hop()
	ch = Channel(capacity=1000, cid="cid0")
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	hop.add_channel(ch)
	assert(ch.is_enabled_in_direction(Direction.Alph))
	assert(not ch.is_enabled_in_direction(Direction.NonAlph))
	ch.set_fee_in_direction(Direction.Alph, FeeType.SUCCESS, base_fee=1, fee_rate=0.01)
	assert ch.in_direction(Direction.Alph).requires_fee_for_body(FeeType.SUCCESS, 100) == 2
	ch_1 = Channel(capacity=2000, cid="cid1", num_slots_per_direction=2)
	hop.add_channel(ch_1)
	assert(hop.has_channel("cid0"))
	assert(hop.has_channel("cid1"))
	assert hop.get_channel("no_such_cid") is None
	ch_1.set_fee_in_direction(Direction.Alph, FeeType.SUCCESS, base_fee=2, fee_rate=0.02)
	assert(len(hop.get_all_channels()) == 2)
	chs_can_forward_1500 = hop.get_channels_with_condition(
		condition=lambda ch: ch.really_can_forward_in_direction_at_time(Direction.Alph, time=0, amount=1500))
	assert(len(chs_can_forward_1500) == 1)
	chs_by_fee_for_100 = hop.get_channels_with_condition(
		sorting_function=lambda ch: ch.in_direction(Direction.Alph).requires_total_fee_for_body(100))
	assert len(chs_by_fee_for_100) == 2
	assert chs_by_fee_for_100[0].capacity == 1000


def test_is_jammed():
	hop = Hop()
	ch = Channel(capacity=1000, cid="cid0")
	ch.enable_direction_with_num_slots(Direction.Alph, num_slots=2)
	hop.add_channel(ch)
	assert(not hop.cannot_forward(Direction.Alph, time=0))
	assert(hop.get_total_num_slots_occupied_in_direction(Direction.Alph) == 0)
	htlc_01 = InFlightHtlc(payment_id="pid1", success_fee=0, desired_result=True)
	htlc_02 = InFlightHtlc(payment_id="pid2", success_fee=0, desired_result=True)
	ch_in_dir_alph = ch.in_direction(Direction.Alph)
	ch_in_dir_alph.push_htlc(resolution_time=1, in_flight_htlc=htlc_01)
	ch_in_dir_alph.push_htlc(resolution_time=1, in_flight_htlc=htlc_02)
	assert hop.cannot_forward(Direction.Alph, time=0)
	assert hop.get_total_num_slots_occupied_in_direction(Direction.Alph) == 2
	assert hop.cannot_forward(Direction.NonAlph, time=0)
	assert hop.get_total_num_slots_occupied_in_direction(Direction.NonAlph) == 0
	# checking jammed status does NOT pop HTLCs!
	assert not hop.cannot_forward(Direction.Alph, time=1)
	assert hop.get_total_num_slots_occupied_in_direction(Direction.Alph) == 2
	assert hop.get_jammed_status(Direction.Alph, time=0) == (True, 2)

from hop import Hop
from channel import Channel
from channelindirection import ChannelInDirection
from enumtypes import FeeType
from direction import Direction
from htlc import InFlightHtlc


def test_hop_create():
	hop = Hop()
	ch = Channel(capacity=1000)
	ch_in_dir_alph = ChannelInDirection(num_slots=2)
	ch.add_ch_in_dir(ch_in_dir_alph, Direction.Alph)
	hop.add_channel(ch, cid="cid0")
	assert(ch.is_enabled_in_direction(Direction.Alph))
	assert(not ch.is_enabled_in_direction(Direction.NonAlph))
	assert(hop.get_cids_enabled_in_direction(Direction.Alph) == ["cid0"])
	assert(hop.get_cids_enabled_in_direction(Direction.NonAlph) == [])
	ch_in_dir_alph.set_fee(FeeType.SUCCESS, base_fee=1, fee_rate=0.01)
	assert(ch.get_total_fee_in_direction(100, Direction.Alph) == 2)
	ch_1 = Channel(capacity=2000, num_slots_per_direction=2)
	hop.add_channel(ch_1, "cid1")
	assert(hop.get_cids() == ["cid0", "cid1"])
	assert(hop.get_cids_can_forward(1500, Direction.Alph) == ["cid1"])
	ch_1.set_fee_in_direction(FeeType.SUCCESS, base_fee=2, fee_rate=0.02, direction=Direction.Alph)
	cids_by_fee = hop.get_cids_can_forward_by_fee(100, Direction.Alph)
	assert(cids_by_fee == ["cid0", "cid1"])
	assert(hop.get_channel("cid3") is None)


def test_is_jammed():
	hop = Hop()
	ch = Channel(capacity=1000)
	ch_in_dir_alph = ChannelInDirection(num_slots=2)
	ch.add_ch_in_dir(ch_in_dir_alph, Direction.Alph)
	hop.add_channel(ch, cid="cid0")
	assert(not hop.is_jammed(Direction.Alph, time=0))
	assert(hop.get_num_slots_occupied(Direction.Alph) == 0)
	htlc_01 = InFlightHtlc(payment_id="pid1", success_fee=0, desired_result=True)
	htlc_02 = InFlightHtlc(payment_id="pid2", success_fee=0, desired_result=True)
	ch_in_dir_alph.store_htlc(resolution_time=1, in_flight_htlc=htlc_01)
	ch_in_dir_alph.store_htlc(resolution_time=1, in_flight_htlc=htlc_02)
	assert(hop.is_jammed(Direction.Alph, time=0))
	assert(hop.get_num_slots_occupied(Direction.Alph) == 2)
	assert(hop.get_jammed_status(Direction.Alph, time=0) == (True, 2))
	assert(hop.get_jammed_status(Direction.NonAlph, time=0) == (True, 0))
	# checking jammed status does NOT pop HTLCs!
	assert(hop.get_jammed_status(Direction.Alph, time=1) == (False, 2))

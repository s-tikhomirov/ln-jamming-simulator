from hop import Hop
from channel import Channel
from chdir import ChannelDirection, dir0, dir1, FeeType


def test_hop_create():
	hop = Hop()
	ch_0 = Channel(capacity=1000)
	ch_dir_0 = ChannelDirection(num_slots=2)
	ch_dir_1 = ChannelDirection(num_slots=2, enabled=False)
	ch_0.add_chdir(ch_dir_0, dir0)
	ch_0.add_chdir(ch_dir_1, dir1)
	hop.add_channel(ch_0, cid="cid0")
	assert(ch_0.is_enabled_in_direction(dir0))
	assert(not ch_0.is_enabled_in_direction(dir1))
	assert(hop.get_cids_enabled_in_direction(dir0) == ["cid0"])
	assert(hop.get_cids_enabled_in_direction(dir1) == [])
	ch_dir_0.set_fee(FeeType.SUCCESS, base_fee=1, fee_rate=0.01)
	assert(ch_0.get_total_fee_in_direction(100, dir0) == 2)
	ch_1 = Channel(capacity=2000, num_slots_per_direction=2)
	hop.add_channel(ch_1, "cid1")
	assert(hop.get_cids() == ["cid0", "cid1"])
	assert(hop.get_cids_can_forward(1500, dir0) == ["cid1"])
	ch_1.set_fee_in_direction(FeeType.SUCCESS, base_fee=2, fee_rate=0.02, direction=dir0)
	cids_by_fee = hop.get_cids_can_forward_by_fee(100, dir0)
	assert(cids_by_fee == ["cid0", "cid1"])
	assert(hop.get_channel("cid3") is None)

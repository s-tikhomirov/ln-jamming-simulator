from chdir import ChannelDirection, FeeType
from channel import Channel
from lnmodel import InFlightHtlc


def test_set_get_fee():
	cd = ChannelDirection(num_slots=2)
	cd.set_fee(FeeType.UPFRONT, base_fee=1, fee_rate=0.01)
	cd.set_fee(FeeType.SUCCESS, base_fee=2, fee_rate=0.02)
	body = 100
	assert(cd.upfront_fee_function(body) == 2)
	assert(cd.success_fee_function(body) == 4)
	success_fee = cd.success_fee_function(body)
	body_plus_success_fee = body + cd.success_fee_function(body)
	upfront_fee = cd.upfront_fee_function(body_plus_success_fee)
	assert(cd.get_total_fee(body) == success_fee + upfront_fee)


def test_is_enabled():
	cd_1 = ChannelDirection(num_slots=2)
	assert(cd_1.is_enabled())
	cd_2 = ChannelDirection(num_slots=2, enabled=False)
	assert(not cd_2.is_enabled())


def test_channel_direction():
	cd = ChannelDirection(num_slots=2)
	# Before adding in-flight payments: all slots are free
	assert(cd.is_empty())
	assert(cd.get_max_num_slots() == 2)
	t_0, htlc_0 = 1, InFlightHtlc("pid", 100, True)
	t_1, htlc_1 = 5, InFlightHtlc("pid", 100, True)
	t_2, htlc_2 = 6, InFlightHtlc("pid", 100, True)
	t_3 = 4
	# Store htlc 0
	has_slot, released_htlcs = cd.ensure_free_slot(t_0)
	assert(has_slot and not released_htlcs)
	cd.store_htlc(t_0, htlc_0)
	# Queue is not full yet
	assert(cd.get_num_slots_occupied() == 1)
	assert(not cd.is_full())
	# Store htlc 1
	has_slot, released_htlcs = cd.ensure_free_slot(t_1)
	assert(has_slot and not released_htlcs)
	cd.store_htlc(t_1, htlc_1)
	# Now the queue is full
	assert(cd.get_num_slots_occupied() == 2)
	assert(cd.is_full())
	# Store htlc 2
	has_slot, released_htlcs = cd.ensure_free_slot(t_2)
	assert(has_slot and released_htlcs)
	resolution_time, released_htlc = released_htlcs[0]
	# We got a free slot by popping an outdated in-flight htlc
	cd.store_htlc(t_2, htlc_2)
	# The queue is full again (popped htlc 1, pushed htlc 2)
	assert(cd.get_num_slots_occupied() == 2)
	assert(cd.is_full())
	# Store htlc 3
	has_slot, released_htlcs = cd.ensure_free_slot(t_3)
	assert(not has_slot and not released_htlcs)
	# Queue is full, and we can't pop anything: can't store htlc 3


def test_reset_with_num_slots():
	cd = ChannelDirection(num_slots=2)
	cd.store_htlc(1, InFlightHtlc("pid", 100, True))
	cd.reset_with_num_slots(3)
	assert(cd.get_num_slots_occupied() == 0)
	assert(cd.get_max_num_slots() == 3)


def test_is_jammed():
	cd = ChannelDirection(num_slots=2)
	cd.store_htlc(1, InFlightHtlc("pid", 100, True))
	cd.store_htlc(1, InFlightHtlc("pid", 100, True))
	assert(cd.get_top_timestamp() == 1)
	assert(cd.is_jammed(time=0))
	cd.reset_with_num_slots(2)
	cd.store_htlc(1, InFlightHtlc("pid", 100, True))
	cd.store_htlc(0, InFlightHtlc("pid", 100, True))
	assert(cd.get_top_timestamp() == 0)
	assert(not cd.is_jammed(time=0))


def test_unsuccessful_ensure_free_slot():
	cd = ChannelDirection(num_slots=2)
	cd.store_htlc(0, InFlightHtlc("pid", 100, True))
	cd.store_htlc(0, InFlightHtlc("pid", 100, True))
	has_slot, released_htlcs = cd.ensure_free_slot(time=0, num_slots_needed=1)
	assert(has_slot and len(released_htlcs) == 1)
	cd.store_htlc(1, InFlightHtlc("pid", 100, True))
	has_slot, released_htlcs = cd.ensure_free_slot(time=0, num_slots_needed=2)
	assert(not has_slot and not released_htlcs)
	assert(cd.get_num_slots_occupied() == 2)

from channel import ChannelDirection
from lnmodel import InFlightHtlc
import pytest

verbose = False


@pytest.fixture
def example_channel_direction():
	cd = ChannelDirection(
		is_enabled=True,
		num_slots=2,
		upfront_base_fee=0,
		upfront_fee_rate=0,
		success_base_fee=0,
		success_fee_rate=0)
	return cd


@pytest.fixture
def example_resolution_times():
	times = (1, 5, 6, 4)
	return times


@pytest.fixture
def example_in_flight_htlcs():
	in_flight_htlcs = (
		InFlightHtlc("pid", 100, True),
		InFlightHtlc("pid", 100, True),
		InFlightHtlc("pid", 100, True),
		InFlightHtlc("pid", 100, True))
	return in_flight_htlcs


def test_channel_direction(example_channel_direction, example_resolution_times, example_in_flight_htlcs):
	cd = example_channel_direction
	# Before adding in-flight payments: all slots are free
	assert(cd.slots.empty())
	assert(cd.slots.maxsize == 2)
	tup_0, tup_1, tup_2, tup_3 = example_in_flight_htlcs
	t_0, t_1, t_2, t_3 = example_resolution_times
	# Store htlc 0
	has_slot, released_htlcs = cd.ensure_free_slot(t_0)
	assert(has_slot and not released_htlcs)
	cd.store_htlc(t_0, tup_0)
	# Queue is not full yet
	assert(cd.slots.qsize() == 1)
	assert(not cd.slots.full())
	# Store htlc 1
	has_slot, released_htlcs = cd.ensure_free_slot(t_1)
	assert(has_slot and not released_htlcs)
	cd.store_htlc(t_1, tup_1)
	# Now the queue is full
	assert(cd.slots.qsize() == 2)
	assert(cd.slots.full())
	# Store htlc 2
	has_slot, released_htlcs = cd.ensure_free_slot(t_2)
	assert(has_slot and released_htlcs)
	resolution_time, released_htlc = released_htlcs[0]
	# We got a free slot by popping an outdated in-flight htlc
	cd.store_htlc(t_2, tup_2)
	# The queue is full again (popped htlc 1, pushed htlc 2)
	assert(cd.slots.qsize() == 2)
	assert(cd.slots.full())
	# Store htlc 3
	has_slot, released_htlcs = cd.ensure_free_slot(t_3)
	assert(not has_slot and not released_htlcs)
	# Queue is full, and we can't pop anything: can't store htlc 3

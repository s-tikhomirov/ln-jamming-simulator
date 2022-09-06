import pytest

from schedule import Schedule, HonestSchedule, JammingSchedule, Event


@pytest.fixture
def example_schedule():
	sch = Schedule(duration=10)
	sch.populate(
		senders_list=["Alice"],
		receivers_list=["Bob"],
		amount_function=lambda: 1000,
		desired_result=True,
		payment_processing_delay_function=lambda: 1,
		payment_generation_delay_function=lambda: 3)
	return sch


def test_schedule_get_put(example_schedule):
	time, event = example_schedule.get_event()
	assert(event is not None)
	assert(time == 0)
	assert(event.sender == "Alice")
	assert(event.receiver == "Bob")
	assert(event.amount == 1000)
	assert(event.processing_delay == 1)
	assert(event.desired_result is True)
	# construct new event
	event_time, new_event = 2, Event("Bob", "Charlie", 2000, 2, False)
	example_schedule.put_event(event_time, new_event, current_time=1)
	time, event = example_schedule.get_event()
	assert(time == 2)
	# we can't compare with == Event(...): id's would be different
	assert(event.sender == "Bob")
	assert(event.receiver == "Charlie")
	assert(event.amount == 2000)
	assert(event.processing_delay == 2)
	assert(event.desired_result is False)


def test_get_all_events():
	sch = Schedule(duration=10)
	assert(sch.get_size() == 0)
	assert(sch.get_event() == (None, None))
	sch.put_event(1, Event("Alice", "Bob", 1000, 2, True))
	sch.put_event(0, Event("Alice", "Bob", 2000, 2, True))
	assert(sch.get_size() == 2)
	all_events = sch.get_all_events()
	assert(sch.is_empty())
	assert(len(all_events) == 2)
	time_1, event_1 = all_events[0]
	time_2, event_2 = all_events[1]
	assert(time_1 == 0)
	assert(event_1.amount == 2000)
	assert(time_2 == 1)
	assert(event_2.amount == 1000)


def test_event_same_sender_receiver():
	# we don't include events into schedule with the same sender and receiver
	sch = Schedule(duration=10)
	sch.populate(
		senders_list=["Alice"],
		receivers_list=["Alice"],
		amount_function=lambda: 1000,
		desired_result=True,
		payment_processing_delay_function=lambda: 1,
		payment_generation_delay_function=lambda: 3)
	assert(sch.is_empty())


def test_populate_schedule_with_one_event():
	sch = Schedule(duration=0)
	sch.populate(
		senders_list=["Alice"],
		receivers_list=["Bob"],
		amount_function=lambda: 1000,
		desired_result=True,
		payment_processing_delay_function=lambda: 1,
		payment_generation_delay_function=lambda: 3)
	assert(sch.get_size() == 1)


def test_generate_honest_schedule():
	h_sch = HonestSchedule(duration=0)
	h_sch.populate(senders_list=["Alice"], receivers_list=["Bob"])
	assert(h_sch.get_size() == 1)
	time, event = h_sch.get_event()
	assert(time == 0)
	assert(event.sender == "Alice")
	assert(event.receiver == "Bob")
	assert(event.desired_result is True)


def test_generate_jamming_schedule():
	j_sch = JammingSchedule(duration=0)
	j_sch.populate()
	assert(j_sch.get_size() == 1)
	time, event = j_sch.get_event()
	assert(time == 0)
	assert(event.sender == "JammerSender")
	assert(event.receiver == "JammerReceiver")
	assert(event.desired_result is False)


def test_generate_jamming_schedule_one_jam_per_each_of_hops():
	j_sch = JammingSchedule(duration=0)
	j_sch.populate(one_jam_per_each_of_hops=(("Alice", "Bob"), ("Charlie", "Dave")))
	assert(j_sch.get_size() == 2)
	all_events = j_sch.get_all_events()
	times = [elem[0] for elem in all_events]
	route_via = [elem[1].must_route_via_nodes for elem in all_events]
	assert(times == [0, 0])
	assert(("Alice", "Bob") in route_via)
	assert(("Charlie", "Dave") in route_via)

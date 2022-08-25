from schedule import Schedule, Event

import pytest


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
	assert(event.sender == "Bob")
	assert(event.receiver == "Charlie")
	assert(event.amount == 2000)
	assert(event.processing_delay == 2)
	assert(event.desired_result is False)

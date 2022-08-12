from schedule import Schedule, Event

import pytest


def example_amount_function():
	return 1000

def example_processing_delay_function():
	return 1

def example_generation_delay_function():
	return 3

@pytest.fixture
def example_schedule():
	sch = Schedule()
	sch.generate_schedule(
		senders_list = ["Alice"],
		receivers_list = ["Bob"],
		amount_function = example_amount_function,
		desired_result = True,
		payment_processing_delay_function = example_processing_delay_function,
		payment_generation_delay_function = example_generation_delay_function,
		scheduled_duration = 10)
	return sch

def test_schedule_get_put(example_schedule):
	time, event = example_schedule.get_event()
	assert(event is not None)
	assert(time == 0)
	assert(event.sender == "Alice")
	assert(event.receiver == "Bob")
	assert(event.amount == 1000)
	assert(event.processing_delay == 1)
	assert(event.desired_result == True)
	# construct new event
	event_time, new_event = 2, Event("Bob", "Charlie", 2000, 2, False)
	example_schedule.put_event(event_time, new_event, current_time=1)
	time, event = example_schedule.get_event()
	#print("Got new event:", time, event)
	assert(time == 2)
	assert(event.sender == "Bob")
	assert(event.receiver == "Charlie")
	assert(event.amount == 2000)
	assert(event.processing_delay == 2)
	assert(event.desired_result == False)

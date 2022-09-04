from event import Event


def test_event():
	event_1 = Event("Alice", "Bob", 100, 1, True)
	event_2 = Event("Alice", "Bob", 100, 1, True, must_route_via_nodes=["Charlie"])
	assert((event_1 < event_2) == (event_1.id < event_2.id))
	assert((event_1 > event_2) != (event_1 < event_2))

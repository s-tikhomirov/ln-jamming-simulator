from node import Node
from payment import Payment

UPFRONT_BASE = 5
UPFRONT_RATE = 0.02
SUCCESS_BASE = 10
SUCCESS_RATE = 0.05

def success_fee_function(a):
	return round(SUCCESS_BASE + SUCCESS_RATE * a)

def upfront_fee_function(a):
	return round(UPFRONT_BASE + UPFRONT_RATE * a)

def time_to_next_function():
	return 1

def time_to_next_function_jam():
	return 10

def amount_function():
	return 100

def delay_function():
	return 0


def test_payment_creation():
	p0 = Payment(None, upfront_fee_function, success_fee_function, body=100)
	p1 = Payment(p0, upfront_fee_function, success_fee_function)
	p2 = Payment(p1, upfront_fee_function, success_fee_function)
	p3 = Payment(p2, upfront_fee_function, success_fee_function)
	assert(p3.amount == 139)
	assert(p2.amount == 123)
	assert(p1.amount == 108)
	assert(p0.amount == 93)
	assert(p3.upfront_fee == 8)
	assert(p2.upfront_fee == 7)
	assert(p1.upfront_fee == 7)
	assert(p0.upfront_fee == 7)
	


def test_multi_hop_payment_success():
	alice = Node("Alice", num_slots=1, prob_network_fail=0, prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function,
		payment_amount_function=amount_function,
		payment_delay_function=delay_function)
	bob = Node("Bob", num_slots=1, prob_network_fail=0, prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function)
	charlie = Node("Charlie", num_slots=1, prob_network_fail=0, prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function)
	route = [alice, bob, charlie]
	p = alice.create_payment(route)
	print(p)
	alice.route_payment(p, route)
	assert(alice.revenue == -22)
	assert(bob.revenue == 15)


def test_multi_hop_payment_fail():
	alice = Node("Alice", num_slots=1, prob_network_fail=0, prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function,
		payment_amount_function=amount_function,
		payment_delay_function=delay_function)
	bob = Node("Bob", num_slots=1, prob_network_fail=0, prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function)
	charlie = Node("Charlie", num_slots=1, prob_network_fail=0, prob_deliberate_fail=1,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function)
	dave = Node("Dave", num_slots=1, prob_network_fail=0, prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=time_to_next_function)
	route = [alice, bob, charlie, dave]
	p = alice.create_payment(route)
	print(p)
	alice.route_payment(p, route)
	print(alice, "\n", bob, "\n", charlie, "\n", dave)
	assert(alice.revenue == -7)
	assert(bob.revenue == 0)
	assert(charlie.revenue == 7)
	assert(dave.revenue == 0)


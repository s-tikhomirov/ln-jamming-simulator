from math import ceil

from node import Node
from payment import Payment


UPFRONT_BASE = 2
UPFRONT_RATE = 0.02
SUCCESS_BASE = 5
SUCCESS_RATE = 0.05

def success_fee_function(a):
	# round() uses "banker's rounding": round ties to nearest EVEN number
	# use ceil to avoid floating-point uncertainties
	return ceil(SUCCESS_BASE + SUCCESS_RATE * a)

def upfront_fee_function(a):
	return ceil(UPFRONT_BASE + UPFRONT_RATE * a)

def time_to_next_function():
	return 1


TEST_AMOUNT = 100
TEST_DELAY = 2


#### PAYMENT TESTS ####

def test_manual_payment_creation():
	"""
		Test simple multi-hop payment creation.
		Here, we don't subtract final-hop upfront fee from what receiver gets.
	"""
	p0 = Payment(None, upfront_fee_function, success_fee_function, receiver_amount=100)
	p1 = Payment(p0, upfront_fee_function, success_fee_function)
	p2 = Payment(p1, upfront_fee_function, success_fee_function)
	print(p2)
	assert(p0.body 			== 100)
	assert(p0.success_fee 	== 0)
	assert(p0.upfront_fee 	== 4)
	assert(p1.body 			== 100)
	assert(p1.success_fee 	== 10)
	assert(p1.upfront_fee 	== 9)
	assert(p2.body 			== 110)
	assert(p2.success_fee 	== 11)
	assert(p2.upfront_fee 	== 14)


#### ROUTING TESTS ####

sender = Node("Sender",
	num_slots=1,
	prob_next_channel_low_balance=0,
	success_fee_function=success_fee_function,
	upfront_fee_function=upfront_fee_function,
	payment_amount_function=lambda : TEST_AMOUNT,
	payment_delay_function=lambda : TEST_DELAY,
	enforce_dust_limit=False
	)

router = Node("Router",
	num_slots=1,
	prob_next_channel_low_balance=0,
	success_fee_function=success_fee_function,
	upfront_fee_function=upfront_fee_function
	)

receiver = Node("Receiver",
	num_slots=1,
	prob_next_channel_low_balance=0,
	success_fee_function=success_fee_function,
	upfront_fee_function=upfront_fee_function,
	)

route = [sender, router, receiver]

def reset_route(route):
	for node in route:
		node.reset()


def test_route_based_payment_creation():
	"""
		Test route-based payment creation.
		Amount generation function is set at node creation.
		The last hop upfront fee is subtracted from amount.
		(This is not the case in "manual" payment generation.)
	"""
	p = sender.create_payment(route)
	assert(p.downstream_payment.body 			== 96)
	assert(p.downstream_payment.success_fee 	== 0)
	assert(p.downstream_payment.upfront_fee 	== 4)
	assert(p.body 			== 96)
	assert(p.success_fee 	== 10)
	assert(p.upfront_fee 	== 9)
	reset_route(route)


def test_payment_routing():
	"""
		Test successful payment routing.
		All success-case and upfront fees are paid.
	"""
	p = sender.create_payment(route)
	sender.route_payment(p, route)
	assert(sender.upfront_revenue 	== -9)
	assert(sender.success_revenue 	== -10)
	assert(router.upfront_revenue 	== 5)
	assert(router.success_revenue 	== 10)
	# payment got to the receiver
	# we discard receiver's upfront fee revenue
	# because it was subtracted from the amount at payment construction
	assert(receiver.upfront_revenue == 0)
	assert(receiver.success_revenue == 0)
	reset_route(route)


def test_payment_rejected_by_router():
	"""
		Test a payment that is rejected by the router.
		The router should get upfront fee from the sender.
	"""
	p = sender.create_payment(route)
	router.prob_next_channel_low_balance = 1
	sender.route_payment(p, route)
	router.prob_next_channel_low_balance = 0
	assert(sender.upfront_revenue 	== -9)
	assert(sender.success_revenue 	== 0)
	assert(router.upfront_revenue 	== 9)
	assert(router.success_revenue 	== 0)
	# the payment didn't get to the receiver
	assert(receiver.upfront_revenue == 0)
	assert(receiver.success_revenue == 0)
	reset_route(route)


def test_payment_rejected_by_receiver():
	"""
		Test a payment deliberately rejected by the receiver.
		All upfront fees are paid, success-case fees are not.
	"""
	p = sender.create_payment(route)
	receiver.prob_deliberately_fail = 1
	sender.route_payment(p, route)
	receiver.prob_deliberately_fail = 0
	assert(sender.upfront_revenue 	== -9)
	assert(sender.success_revenue 	== 0)
	assert(router.upfront_revenue 	== 5)
	assert(router.success_revenue 	== 0)
	# the payment got to the receiver (jammer) but was rejected
	# we count upfront fee for failed payment as revenue
	assert(receiver.upfront_revenue == 4)
	assert(receiver.success_revenue == 0)
	reset_route(route)


def test_slots():
	"""
		Check that a routing node with the (only) slot occupied cannot take another payment.
	"""
	p = sender.create_payment(route)
	sender.route_payment(p, route)
	# payment delay is 2 but time to next is 1
	# when the next payment (potentially) arrives
	assert(sender.upfront_revenue 	== -9)
	assert(sender.success_revenue 	== -10)
	assert(router.upfront_revenue 	== 5)
	assert(router.success_revenue 	== 10)
	# the router's only slot is busy for 1 more second
	assert(router.slot_leftovers == [1])
	sender.route_payment(p, route)
	# the next payment is failed by the sender because the router doesn't have free slots
	assert(sender.upfront_revenue 	== -9)
	assert(sender.success_revenue 	== -10)
	assert(router.upfront_revenue 	== 5)
	assert(router.success_revenue 	== 10)
	assert(router.slot_leftovers == [0])
	sender.route_payment(p, route)
	assert(sender.upfront_revenue 	== -18)
	assert(sender.success_revenue 	== -20)
	assert(router.upfront_revenue 	== 10)
	assert(router.success_revenue 	== 20)
	assert(router.slot_leftovers == [1])

	
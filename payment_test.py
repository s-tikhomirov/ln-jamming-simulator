from payment import Payment
from math import ceil
import pytest

@pytest.fixture
def example_payment_upfront_fee_function():
	# For the simplest example, we want to use integerd
	# to avoid floating-point uncertainties.
	# We use ceil() and not round() here:
	# round() uses "banker's rounding": round ties to nearest EVEN number
	# (which is counterintuitive)
	upfront_base = 2
	upfront_rate = 0.02
	return lambda a : ceil(upfront_base + a * upfront_rate)

@pytest.fixture
def example_payment_success_fee_function():
	success_base = 5
	success_rate = 0.05
	return lambda a : ceil(success_base + a * success_rate)


def test_manual_payment_creation(example_payment_upfront_fee_function, example_payment_success_fee_function):
	"""
		Test simple multi-hop payment creation.
		Here, we don't subtract final-hop upfront fee from what receiver gets.
	"""
	p0 = Payment(
		downstream_payment = None,
		upfront_fee_function = example_payment_upfront_fee_function,
		success_fee_function = example_payment_success_fee_function,
		desired_result = True,
		processing_delay = 1,
		receiver_amount = 100)
	p1 = Payment(p0, example_payment_upfront_fee_function, example_payment_success_fee_function)
	p2 = Payment(p1, example_payment_upfront_fee_function, example_payment_success_fee_function)
	for p in [p0, p1, p2]:	
		assert(p0.processing_delay 	== 1)
		assert(p0.desired_result == True)
	assert(p0.body 			== 100)
	assert(p0.success_fee 	== 0)
	assert(p0.upfront_fee 	== 4)
	assert(p1.body 			== 100)
	assert(p1.success_fee 	== 10)
	assert(p1.upfront_fee 	== 9)
	assert(p2.body 			== 110)
	assert(p2.success_fee 	== 21)
	assert(p2.upfront_fee 	== 14)
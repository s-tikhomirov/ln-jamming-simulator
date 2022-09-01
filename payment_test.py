from payment import Payment
from lnmodel import LNModel
from simulator import Simulator

from math import ceil, isclose
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
	return lambda a: ceil(upfront_base + a * upfront_rate)


@pytest.fixture
def example_payment_success_fee_function():
	success_base = 5
	success_rate = 0.05
	return lambda a: ceil(success_base + a * success_rate)


def test_manual_payment_creation(example_payment_upfront_fee_function, example_payment_success_fee_function):
	'''
		Test simple multi-hop payment creation.
		Here, we don't subtract final-hop upfront fee from what receiver gets.
	'''
	p_cd = Payment(
		downstream_payment=None,
		downstream_node=None,
		upfront_fee_function=example_payment_upfront_fee_function,
		success_fee_function=example_payment_success_fee_function,
		desired_result=True,
		processing_delay=1,
		receiver_amount=100)
	p_bc = Payment(p_cd, "Charlie", example_payment_upfront_fee_function, example_payment_success_fee_function)
	p_ab = Payment(p_bc, "Bob", example_payment_upfront_fee_function, example_payment_success_fee_function)
	for p in [p_ab, p_bc, p_cd]:
		assert(p.processing_delay == 1)
		assert(p.desired_result is True)
	assert(p_ab.body == 110)
	assert(p_ab.success_fee == 21)
	assert(p_ab.upfront_fee == 14)
	assert(p_ab.downstream_node == "Bob")
	assert(p_bc.body == 100)
	assert(p_bc.success_fee == 10)
	assert(p_bc.upfront_fee == 9)
	assert(p_bc.downstream_node == "Charlie")
	assert(p_cd.body == 100)
	assert(p_cd.success_fee == 0)
	assert(p_cd.upfront_fee == 4)
	assert(p_cd.downstream_node is None)


@pytest.fixture
def example_snapshot_json():
	channel_ABx0 = {
		"source": "Alice",
		"destination": "Bob",
		"short_channel_id": "ABx0",
		"satoshis": 1000000,
		"active": True,
		"base_fee_millisatoshi": 5000,
		"fee_per_millionth": 50000,
		"base_fee_millisatoshi_upfront": 2000,
		"fee_per_millionth_upfront": 20000
	}
	channel_BCx0 = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx0",
		"satoshis": 1000000,
		"active": True,
		"base_fee_millisatoshi": 5000,
		"fee_per_millionth": 50000,
		"base_fee_millisatoshi_upfront": 2000,
		"fee_per_millionth_upfront": 20000
	}
	channel_CDx0 = {
		"source": "Charlie",
		"destination": "Dave",
		"short_channel_id": "CDx0",
		"satoshis": 1000000,
		"active": True,
		"base_fee_millisatoshi": 5000,
		"fee_per_millionth": 50000,
		"base_fee_millisatoshi_upfront": 2000,
		"fee_per_millionth_upfront": 20000
	}
	snapshot_json = {"channels": [channel_ABx0, channel_BCx0, channel_CDx0]}
	return snapshot_json


@pytest.fixture
def example_ln_model(example_snapshot_json):
	return LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True,
		keep_receiver_upfront_fee=True)


def test_route_payment_creation(example_ln_model):
	route = ["Alice", "Bob", "Charlie", "Dave"]
	sim = Simulator(
		example_ln_model,
		target_hops=("Bob", "Charlie"),
		max_num_attempts_per_route_honest=1,
		max_num_attempts_per_route_jamming=1,
		max_num_routes_honest=1,
		max_num_routes_jamming=1,)
	p = sim.create_payment(
		route,
		amount=100,
		processing_delay=2,
		desired_result=True,
		enforce_dust_limit=False)
	dsp = p.downstream_payment
	ddsp = dsp.downstream_payment
	assert(p.amount == 130.5)
	assert(p.success_fee == 20.5)
	assert(p.body == 110)
	assert(isclose(p.upfront_fee, 12.81))
	assert(dsp.amount == 110)
	assert(dsp.body == 100)
	assert(dsp.success_fee == 10)
	assert(dsp.upfront_fee == 8.2)
	assert(ddsp.amount == ddsp.body == 100)
	assert(ddsp.success_fee == 0)
	assert(ddsp.upfront_fee == 4)

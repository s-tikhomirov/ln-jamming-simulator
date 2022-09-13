from math import ceil
import pytest
import json
from functools import partial

from lnmodel import LNModel
from enumtypes import FeeType
from simulator import JammingSimulator, HonestSimulator
from params import PaymentFlowParams, FeeParams
from schedule import HonestSchedule, JammingSchedule

import logging
logger = logging.getLogger(__name__)

WHEEL_SNAPSHOT_FILENAME = "./snapshots/listchannels_wheel.json"

DEFAULT_NUM_SLOTS_PER_CHANNEL_IN_DIRECTION = 5


def get_example_ln_model():
	with open(WHEEL_SNAPSHOT_FILENAME, 'r') as snapshot_file:
		snapshot_json = json.load(snapshot_file)
	ln_model = LNModel(snapshot_json, default_num_slots_per_channel_in_direction=DEFAULT_NUM_SLOTS_PER_CHANNEL_IN_DIRECTION, no_balance_failures=True)
	ln_model.set_fee_for_all(
		FeeType.SUCCESS,
		base=FeeParams["SUCCESS_BASE"],
		rate=FeeParams["SUCCESS_RATE"])
	return ln_model


@pytest.fixture
def example_j_sim():
	ln_model = get_example_ln_model()
	sim = JammingSimulator(
		ln_model,
		target_hops=[("Mary", "Charlie")],
		max_num_attempts_per_route=500,
		max_num_routes=1,
		num_runs_per_simulation=1)
	return sim


@pytest.fixture
def example_h_sim():
	ln_model = get_example_ln_model()
	sim = HonestSimulator(
		ln_model,
		max_num_attempts_per_route=1,
		max_num_routes=1,
		num_runs_per_simulation=1,
		subtract_last_hop_upfront_fee_for_honest_payments=True)
	return sim


def test_simulator_jamming_schedule(example_j_sim):
	# order of target hop is important to invoke looped route logic
	target_hops = [("Charlie", "Hub"), ("Hub", "Bob"), ("Alice", "Hub"), ("Hub", "Dave")]
	schedule_generation_function_jamming = partial(
		lambda duration: JammingSchedule(
			duration=duration,
			hop_to_jam_with_own_batch=target_hops))
	simulator = example_j_sim
	simulator.target_hops = target_hops
	simulator.max_num_routes = 10
	# we need an odd number of slots to test this behavior
	# i.e.: unjammed slot in two-loop route failed at the second loop
	assert(simulator.ln_model.default_num_slots_per_channel_in_direction % 2 == 1)
	simulator.ln_model.add_jammers_channels(
		send_to_nodes=["Alice", "Charlie", "Hub"],
		receive_from_nodes=["Dave", "Hub"],
		num_slots=(DEFAULT_NUM_SLOTS_PER_CHANNEL_IN_DIRECTION + 1) * len(target_hops))
	duration = 1
	results = simulator.run_simulation_series(
		schedule_generation_function_jamming,
		duration=duration,
		upfront_base_coeff_range=[0.001],
		upfront_rate_coeff_range=[0.1])
	logger.info(f"{results}")
	assert(results is not None)
	assert_jam_results_correctness(simulator, duration, results)


def test_simulator_honest_schedule(example_h_sim):
	schedule_generation_function_honest = partial(
		lambda duration: HonestSchedule(
			duration=duration,
			senders=["Alice"],
			receivers=["Bob"],
			must_route_via_nodes=["Hub"]))
	simulator = example_h_sim
	results = simulator.run_simulation_series(
		schedule_generation_function_honest,
		duration=300,
		upfront_base_coeff_range=[0, 0.001],
		upfront_rate_coeff_range=[0, 0.1])
	logger.info(f"{results}")
	assert(results is not None)
	for res in results:
		stats = res["stats"]
		revenues = res["revenues"]
		assert(stats["num_failed"] <= stats["num_sent"])
		assert(stats["num_reached_receiver"] <= stats["num_sent"])
		if simulator.num_runs_per_simulation == 1:
			assert(stats["num_sent"] == stats["num_failed"] + stats["num_reached_receiver"])
		stats["num_reached_receiver"] <= stats["num_sent"]
		assert(stats["num_sent"] > 0)
		assert(revenues["Alice"] < 0)
		assert(revenues["Bob"] >= 0)
		assert(revenues["Charlie"] == 0)
		assert(revenues["Dave"] == 0)
		assert(revenues["Hub"] > 0)
		if res["upfront_base_coeff"] == 0 and res["upfront_rate_coeff"] == 0:
			assert(revenues["Bob"] == 0)
		if res["upfront_base_coeff"] > 0 or res["upfront_rate_coeff"] > 0:
			assert(revenues["Bob"] > 0)


def test_simulator_jamming_fixed_route(example_j_sim):
	target_hops = [("Alice", "Hub"), ("Hub", "Dave")]
	schedule_generation_function_jamming = partial(
		lambda duration: JammingSchedule(
			duration=duration))
	simulator = example_j_sim
	simulator.target_hops = target_hops
	simulator.jammer_must_route_via_nodes = ["Alice", "Hub", "Dave"]
	simulator.ln_model.add_jammers_channels(
		send_to_nodes=["Alice"],
		receive_from_nodes=["Dave"],
		num_slots=(DEFAULT_NUM_SLOTS_PER_CHANNEL_IN_DIRECTION + 1) * len(target_hops))
	duration = 8
	results = simulator.run_simulation_series(
		schedule_generation_function_jamming,
		duration=duration,
		upfront_base_coeff_range=[0],
		upfront_rate_coeff_range=[0])
	assert_jam_results_correctness(simulator, duration, results)


def assert_jam_results_correctness(simulator, duration, results):
	# the number of jams is constant and pre-determined if no_balance_failures is True
	expected_num_jam_batches = int(ceil(duration / PaymentFlowParams["JAM_DELAY"]))
	expected_num_jams = expected_num_jam_batches * (simulator.ln_model.default_num_slots_per_channel_in_direction + 1)
	for res in results:
		stats = res["stats"]
		revenues = res["revenues"]
		assert(stats["num_failed"] == stats["num_sent"])
		assert(stats["num_reached_receiver"] <= stats["num_sent"])
		if simulator.max_num_routes == 1:
			assert(stats["num_sent"] == expected_num_jams)
		else:
			assert(stats["num_sent"] >= expected_num_jams)
		if res["upfront_base_coeff"] == 0 and res["upfront_rate_coeff"] == 0:
			assert(revenues["Dave"] == 0)

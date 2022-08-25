from experiment import Experiment
from lnmodel import LNModel, FeeType
from simulator import Simulator
from schedule import generate_honest_schedule, generate_jamming_schedule
from params import PaymentFlowParams

from math import floor
from functools import partial
import pytest


@pytest.fixture
def success_base_fee():
	return 1


@pytest.fixture
def success_fee_rate():
	return 5 / (1000 * 1000)


@pytest.fixture
def example_ln_model(success_base_fee, success_fee_rate):
	channel_ABx0 = {
		"source": "Alice",
		"destination": "Bob",
		"short_channel_id": "ABx0",
		"satoshis": 1000000,
		"active": True
	}
	channel_BCx0 = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx0",
		"satoshis": 1000000,
		"active": True
	}
	channel_CDx0 = {
		"source": "Charlie",
		"destination": "Dave",
		"short_channel_id": "CDx0",
		"satoshis": 1000000,
		"active": True
	}
	snapshot_json = {"channels": [channel_ABx0, channel_BCx0, channel_CDx0]}
	ln_model = LNModel(snapshot_json, default_num_slots=5)
	ln_model.add_edge(
		src="JammerSender",
		dst="Bob",
		capacity=1000000,
		is_enabled=True,
		num_slots_multiplier=2)
	ln_model.add_edge(
		src="Charlie",
		dst="JammerReceiver",
		capacity=1000000,
		is_enabled=True,
		num_slots_multiplier=2)
	ln_model.set_fee_for_all(
		FeeType.SUCCESS,
		success_base_fee,
		success_fee_rate)
	return ln_model


@pytest.fixture
def example_ln_model_small(success_base_fee, success_fee_rate):
	channel_ABx0 = {
		"source": "Alice",
		"destination": "Bob",
		"short_channel_id": "ABx0",
		"satoshis": 1000000,
		"active": True
	}
	channel_BCx0 = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx0",
		"satoshis": 1000,
		"active": True
	}
	channel_CDx0 = {
		"source": "Charlie",
		"destination": "Dave",
		"short_channel_id": "CDx0",
		"satoshis": 1000000,
		"active": True
	}
	snapshot_json = {"channels": [channel_ABx0, channel_BCx0, channel_CDx0]}
	ln_model = LNModel(snapshot_json, default_num_slots=5)
	ln_model.add_edge(
		src="JammerSender",
		dst="Bob",
		capacity=1000000,
		is_enabled=True,
		num_slots_multiplier=2)
	ln_model.add_edge(
		src="Charlie",
		dst="JammerReceiver",
		capacity=1000000,
		is_enabled=True,
		num_slots_multiplier=2)
	ln_model.set_fee_for_all(
		FeeType.SUCCESS,
		success_base_fee,
		success_fee_rate)
	return ln_model


@pytest.fixture
def example_simulator():
	simulator = Simulator(
		no_balance_failures=True,
		keep_receiver_upfront_fee=True,
		max_num_attempts_per_route_honest=10,
		max_num_attempts_per_route_jamming=100)
	return simulator


@pytest.fixture
def example_experiment(example_ln_model, example_simulator):
	experiment = Experiment(
		example_ln_model,
		example_simulator,
		num_runs_per_simulation=1)
	return experiment


@pytest.fixture
def example_experiment_small(example_ln_model_small, example_simulator):
	experiment = Experiment(
		example_ln_model_small,
		example_simulator,
		num_runs_per_simulation=1)
	return experiment


@pytest.fixture
def simulation_duration():
	return 60


@pytest.fixture
def schedule_generation_function_honest(simulation_duration):
	return partial(lambda: generate_honest_schedule(
		senders_list=["Alice"],
		receivers_list=["Dave"],
		duration=simulation_duration))


@pytest.fixture
def schedule_generation_function_jamming(simulation_duration):
	return partial(lambda: generate_jamming_schedule(
		duration=simulation_duration,
		must_route_via=["Bob", "Charlie"]))


def test_experiment_no_balance_failures(
	example_experiment,
	schedule_generation_function_honest,
	schedule_generation_function_jamming,
	simulation_duration):
	experiment = example_experiment
	results_honest, results_jamming = experiment.run_pair_of_simulations(
		schedule_generation_function_honest,
		schedule_generation_function_jamming,
		upfront_base_coeff_range=[0, 0.01],
		upfront_rate_coeff_range=[0, 0.1])
	results = {
		"simulations": {
			"honest": results_honest,
			"jamming": results_jamming
		}
	}
	assert_results_correctness(experiment, simulation_duration, results)


def test_experiment_balance_failures_multiple_jamming_attempts(
	example_experiment_small,
	schedule_generation_function_honest,
	schedule_generation_function_jamming,
	simulation_duration):
	experiment = example_experiment_small
	experiment.simulator.no_balance_failures = False
	results_honest, results_jamming = experiment.run_pair_of_simulations(
		schedule_generation_function_honest,
		schedule_generation_function_jamming,
		upfront_base_coeff_range=[0, 0.01],
		upfront_rate_coeff_range=[0, 0.1])
	results = {
		"simulations": {
			"honest": results_honest,
			"jamming": results_jamming
		}
	}
	assert_results_correctness(experiment, simulation_duration, results)


def assert_results_correctness(experiment, simulation_duration, results):
	# the number of jams is constant and pre-determined if no_balance_failures is True
	expected_num_jams = int(1 + floor(simulation_duration / PaymentFlowParams["JAM_DELAY"])) * \
	(experiment.ln_model.default_num_slots + 1)
	rh, rj = results["simulations"]["honest"], results["simulations"]["jamming"]

	for res in rh:
		stats = res["stats"]
		revenues = res["revenues"]
		assert(stats["num_failed"] <= stats["num_sent"])
		assert(stats["num_reached_receiver"] <= stats["num_sent"])
		if experiment.num_runs_per_simulation == 1:
			assert(stats["num_sent"] == stats["num_failed"] + stats["num_reached_receiver"])
		stats["num_reached_receiver"] <= stats["num_sent"]
		if stats["num_sent"] > 0:
			assert(revenues["Alice"] < 0)
			assert(revenues["Bob"] > 0)
			assert(revenues["Charlie"] > 0)
		else:
			assert(revenues["Alice"] == 0)
			assert(revenues["Bob"] == 0)
			assert(revenues["Charlie"] == 0)
		if not experiment.simulator.keep_receiver_upfront_fee or (
			res["upfront_base_coeff"] == 0 and res["upfront_rate_coeff"] == 0):
			assert(revenues["Dave"] == 0)
		if experiment.simulator.keep_receiver_upfront_fee:
			if (res["upfront_base_coeff"] > 0 or res["upfront_rate_coeff"] > 0) and stats["num_sent"] > 0:
				assert(revenues["Dave"] > 0)
				assert(revenues["Alice"] < 0)
				assert(revenues["Bob"] > 0)
				assert(revenues["Charlie"] > 0)
		else:
			assert(revenues["Dave"] == 0)

	for res in rj:
		stats = res["stats"]
		revenues = res["revenues"]
		assert(stats["num_failed"] == stats["num_sent"])
		assert(stats["num_reached_receiver"] <= stats["num_sent"])
		if experiment.simulator.max_num_attempts_per_route_jamming == 1:
			assert(stats["num_sent"] == expected_num_jams)
		else:
			assert(stats["num_sent"] >= expected_num_jams)
		if not experiment.simulator.keep_receiver_upfront_fee or (
			res["upfront_base_coeff"] == 0 and res["upfront_rate_coeff"] == 0):
			assert(revenues["Dave"] == 0)

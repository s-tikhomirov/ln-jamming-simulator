from experiment import Experiment
from lnmodel import LNModel

from math import floor
import pytest


@pytest.fixture
def example_snapshot_json():
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
	return snapshot_json


@pytest.fixture
def example_experiment(example_snapshot_json):
	example_ln_model = LNModel(example_snapshot_json, default_num_slots=5)
	experiment = Experiment(
		example_ln_model,
		simulation_duration=60,
		num_runs_per_simulation=1,
		success_base_fee=1,
		success_fee_rate=5 / (1000 * 1000),
		no_balance_failures=True,
		keep_receiver_upfront_fee=True,
		default_num_slots=5,
		max_num_attempts_per_route_honest=1,
		max_num_attempts_per_route_jamming=1)
	experiment.set_sender("Alice")
	experiment.set_receiver("Dave")
	experiment.set_target_node_pair("Bob", "Charlie")
	return experiment


def test_experiment_no_balance_failures(example_experiment):
	experiment = example_experiment
	simulation_duration, default_num_slots = 60, 5
	experiment.simulation_duration = simulation_duration
	experiment.default_num_slots = default_num_slots
	upfront_base_coeff_range = [0, 0.002, 0.01]
	upfront_rate_coeff_range = [0, 0.1, 1]
	experiment.run_simulations(upfront_base_coeff_range, upfront_rate_coeff_range)
	assert_results_correctness(experiment, simulation_duration, default_num_slots)


def test_experiment_balance_failures_multiple_jamming_attempts(example_experiment):
	experiment = example_experiment
	# The results with balance failures but with multiple jamming retries
	# should be structurally the same as with one attempt without balance failures
	experiment.no_balance_failures = False
	experiment.max_num_attempts_per_route_jamming = 100
	simulation_duration, default_num_slots = 60, 5
	experiment.simulation_duration = simulation_duration
	experiment.default_num_slots = default_num_slots
	upfront_base_coeff_range = [0, 0.002, 0.01]
	upfront_rate_coeff_range = [0, 0.1, 1]
	experiment.run_simulations(upfront_base_coeff_range, upfront_rate_coeff_range)
	assert_results_correctness(experiment, simulation_duration, default_num_slots)


def assert_results_correctness(experiment, simulation_duration, default_num_slots):
	# the number of jams is constant and pre-determined if no_balance_failures is True
	expected_num_jams = int(1 + floor(simulation_duration / experiment.jam_delay)) * (default_num_slots + 1)
	for i in range(len(experiment.results["simulations"])):
		stats = experiment.results["simulations"][i]["stats"]
		assert(stats["honest"]["num_failed"] <= stats["honest"]["num_sent"])
		if experiment.num_runs_per_simulation == 1 and experiment.max_num_attempts_per_route_jamming == 1:
			assert(stats["honest"]["num_sent"] == stats["honest"]["num_failed"] + stats["honest"]["num_reached_receiver"])
			assert(stats["jamming"]["num_sent"] == expected_num_jams)
			assert(stats["jamming"]["num_failed"] == stats["jamming"]["num_sent"])
		else:
			assert(stats["honest"]["num_sent"] == stats["honest"]["num_failed"] + stats["honest"]["num_reached_receiver"])
			assert(stats["jamming"]["num_sent"] >= expected_num_jams)
			assert(stats["jamming"]["num_failed"] == stats["jamming"]["num_sent"])
		for experiment_type in ("honest", "jamming"):
			assert(stats[experiment_type]["num_reached_receiver"] <= stats[experiment_type]["num_sent"])

	# everyone's revenue under jamming is zero with zero upfront fees
	zero_upfront_fee_result = [r for r in experiment.results["simulations"] if (
		r["upfront_base_coeff"] == 0 and r["upfront_rate_coeff"] == 0)]
	jamming_revenues = zero_upfront_fee_result[0]["revenues"]["jamming"]
	for node in ("Alice", "Bob", "Charlie", "Dave"):
		assert(jamming_revenues[node] == 0)
	# sender's balance is non-positive, others' revenues are non-negative
	for r in experiment.results["simulations"]:
		if stats["honest"]["num_sent"] > 0:
			assert(r["revenues"]["honest"]["Alice"] < 0)
			assert(r["revenues"]["honest"]["Bob"] > 0)
			assert(r["revenues"]["honest"]["Charlie"] > 0)
		else:
			assert(r["revenues"]["honest"]["Alice"] == 0)
			assert(r["revenues"]["honest"]["Bob"] == 0)
			assert(r["revenues"]["honest"]["Charlie"] == 0)
		if not experiment.keep_receiver_upfront_fee or (
			r["upfront_base_coeff"] == 0 and r["upfront_rate_coeff"] == 0):
			assert(r["revenues"]["honest"]["Dave"] == 0)
		else:
			if (r["upfront_base_coeff"] > 0 or r["upfront_rate_coeff"] > 0) and stats["honest"]["num_sent"] > 0:
				assert(r["revenues"]["honest"]["Dave"] > 0)
				assert(r["revenues"]["jamming"]["Alice"] < 0)
				assert(r["revenues"]["jamming"]["Bob"] > 0)
				assert(r["revenues"]["jamming"]["Charlie"] > 0)
				if not experiment.keep_receiver_upfront_fee:
					assert(r["revenues"]["jamming"]["Dave"] == 0)
				else:
					assert(r["revenues"]["jamming"]["Dave"] > 0)

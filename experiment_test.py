from experiment import Experiment

import pytest

from math import floor


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
	snapshot_json = {"channels" : [channel_ABx0, channel_BCx0, channel_CDx0]}
	return snapshot_json


@pytest.fixture
def example_experiment(example_snapshot_json):
	experiment = Experiment(
		example_snapshot_json,
		simulation_duration = 60,
		num_simulations = 1,
		success_base_fee = 1,
		success_fee_rate = 5 / (1000 * 1000),
		no_balance_failures = True,
		keep_receiver_upfront_fee = True,
		default_num_slots = 5,
		max_num_attempts_per_route = 1)
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

	# the number of jams is constant and pre-determined if no_balance_failures is True
	expected_num_jams = int(1 + floor(simulation_duration / experiment.jam_delay)) * (default_num_slots + 1)
	for i in range(len(experiment.results["results"])):
		stats = experiment.results["results"][i]["stats"]
		assert(stats["honest"]["num_failed"] <= stats["honest"]["num_sent"])
		if example_experiment.num_simulations == 1:
			assert(stats["honest"]["num_sent"] == stats["honest"]["num_failed"] + stats["honest"]["num_reached_receiver"])
			assert(stats["jamming"]["num_sent"] == expected_num_jams)
			assert(stats["jamming"]["num_failed"] == stats["jamming"]["num_sent"])
		for experiment_type in ("honest", "jamming"):
			assert(stats[experiment_type]["num_reached_receiver"] <= stats[experiment_type]["num_sent"])

	# everyone's revenue under jamming is zero with zero upfront fees
	zero_upfront_fee_result = [r for r in experiment.results["results"] if (
		r["upfront_base_coeff"] == 0 and r["upfront_rate_coeff"] == 0)]
	jamming_revenues = zero_upfront_fee_result[0]["revenues"]["jamming"]
	
	# sender's balance is non-positive, others' revenues are non-negative
	for r in experiment.results["results"]:
		assert(r["revenues"]["honest"]["Alice"] < 0)
		assert(r["revenues"]["honest"]["Bob"] > 0)
		assert(r["revenues"]["honest"]["Charlie"] > 0)
		if not experiment.keep_receiver_upfront_fee or (
			r["upfront_base_coeff"] == 0 and r["upfront_rate_coeff"] == 0):
			assert(r["revenues"]["honest"]["Dave"] == 0)
		else:
			assert(r["revenues"]["honest"]["Dave"] > 0)
		if r["upfront_base_coeff"] > 0 or r["upfront_rate_coeff"] > 0:
			assert(r["revenues"]["jamming"]["Alice"] < 0)
			assert(r["revenues"]["jamming"]["Bob"] > 0)
			assert(r["revenues"]["jamming"]["Charlie"] > 0)
			if not experiment.keep_receiver_upfront_fee:
				assert(r["revenues"]["jamming"]["Dave"] == 0)
			else:
				assert(r["revenues"]["jamming"]["Dave"] > 0)

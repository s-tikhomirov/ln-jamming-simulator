from experiment import Experiment
from params import FeeParams, ProtocolParams

import argparse
from time import time
from random import seed

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


DEFAULT_UPFRONT_BASE_COEFF_RANGE = [0, 0.001, 0.002, 0.005, 0.01]
DEFAULT_UPFRONT_RATE_COEFF_RANGE = [0, 0.1, 0.2, 0.5, 1]


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--simulation_duration",
		default=60,
		type=int,
		help="Simulation duration in seconds."
	)
	parser.add_argument(
		"--num_runs_per_simulation",
		default=10,
		type=int,
		help="The number of simulation runs per parameter combinaiton."
	)
	parser.add_argument(
		"--success_base_fee",
		default=FeeParams["SUCCESS_BASE"],
		type=int,
		help="Success-case base fee in satoshis (same for all channels)."
	)
	parser.add_argument(
		"--success_fee_rate",
		default=FeeParams["SUCCESS_RATE"],
		type=float,
		help="Success-case fee rate per million (same for all channels)."
	)
	parser.add_argument(
		"--default_num_slots",
		default=ProtocolParams["NUM_SLOTS"],
		type=int,
		help="Number of slots for honest channels (attackes has twice as many)."
	)
	parser.add_argument(
		"--max_num_attempts_honest",
		default=1,
		type=int,
		help="Number of attempts per honest payment in case of balance or deliberate failures."
	)
	parser.add_argument(
		"--max_num_attempts_jamming",
		default=100,
		type=int,
		help="Number of attempts per jam payment in case of balance or deliberate failures."
	)
	parser.add_argument(
		"--no_balance_failures",
		dest="no_balance_failures",
		default=False,
		action="store_true"
	)
	parser.add_argument(
		"--keep_receiver_upfront_fee",
		dest="keep_receiver_upfront_fee",
		default=True,
		action="store_true"
	)
	parser.add_argument(
		"--upfront_base_coeff_range",
		nargs="*",
		type=float,
		default=DEFAULT_UPFRONT_BASE_COEFF_RANGE,
		help="A list of values for upfront base fee coefficient.")
	parser.add_argument(
		"--upfront_rate_coeff_range",
		nargs="*",
		type=float,
		default=DEFAULT_UPFRONT_RATE_COEFF_RANGE,
		help="A list of values for upfront base fee coefficient.")
	parser.add_argument(
		"--seed",
		type=int,
		help="Seed for randomness initialization."
	)
	args = parser.parse_args()

	if args.seed is not None:
		print("Initializing randomness seed:", args.seed)
		seed(args.seed)

	experiment = Experiment(
		snapshot_json,
		args.simulation_duration,
		args.num_runs_per_simulation,
		args.success_base_fee,
		args.success_fee_rate,
		args.no_balance_failures,
		args.keep_receiver_upfront_fee,
		args.default_num_slots,
		args.max_num_attempts_honest,
		args.max_num_attempts_jamming)

	experiment.set_sender("Alice")
	experiment.set_receiver("Dave")
	experiment.set_target_node_pair("Bob", "Charlie")

	start_timestamp = int(time())
	experiment.run_simulations(args.upfront_base_coeff_range, args.upfront_rate_coeff_range)
	end_timestamp = int(time())

	running_time = end_timestamp - start_timestamp
	experiment.results_to_json_file(end_timestamp)
	experiment.results_to_csv_file(end_timestamp)
	print("\nRunning time (min):", round(running_time / 60, 1))


if __name__ == "__main__":
	main()

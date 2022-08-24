from experiment import Experiment
from params import FeeParams, ProtocolParams, PaymentFlowParams
from lnmodel import LNModel, RevenueType
from simulator import Simulator
from schedule import generate_honest_schedule, generate_jamming_schedule

import argparse
from time import time
from random import seed
import json
import csv

DEFAULT_UPFRONT_BASE_COEFF_RANGE = [0, 0.001, 0.002, 0.005, 0.01]
DEFAULT_UPFRONT_RATE_COEFF_RANGE = [0, 0.1, 0.2, 0.5, 1]

ABCD_SNAPSHOT_FILENAME = "./snapshots/listchannels_abcd.json"
WHEEL_SNAPSHOT_FILENAME = "./snapshots/listchannels_wheel.json"


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--scenario",
		type=str,
		choices={"abcd", "wheel"},
		help="LN graph JSON filename."
	)
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
		help="A list of values for upfront base fee coefficient."
	)
	parser.add_argument(
		"--upfront_rate_coeff_range",
		nargs="*",
		type=float,
		default=DEFAULT_UPFRONT_RATE_COEFF_RANGE,
		help="A list of values for upfront base fee coefficient."
	)
	parser.add_argument(
		"--seed",
		type=int,
		help="Seed for randomness initialization."
	)
	args = parser.parse_args()

	if args.seed is not None:
		print("Initializing randomness seed:", args.seed)
		seed(args.seed)

	simulator = Simulator(
		max_num_attempts_per_route_honest=args.max_num_attempts_honest,
		max_num_attempts_per_route_jamming=args.max_num_attempts_jamming,
		no_balance_failures=args.no_balance_failures,
		enforce_dust_limit=True,
		keep_receiver_upfront_fee=args.keep_receiver_upfront_fee)

	def run_linear_experiments():
		with open(ABCD_SNAPSHOT_FILENAME, 'r') as snapshot_file:
			snapshot_json = json.load(snapshot_file)

		ln_model = LNModel(snapshot_json, args.default_num_slots)
		ln_model.set_fee_for_all(
			RevenueType.SUCCESS,
			args.success_base_fee,
			args.success_fee_rate)

		experiment = Experiment(
			ln_model,
			simulator,
			args.num_runs_per_simulation)

		def schedule_generation_funciton_honest():
			return generate_honest_schedule(
				senders_list=["Alice"],
				receivers_list=["Dave"],
				duration=args.simulation_duration)

		def schedule_generation_funciton_jamming():
			return generate_jamming_schedule(
				sender="Alice",
				receiver="Dave",
				duration=args.simulation_duration,
				must_route_via=["Bob", "Charlie"])

		results_honest, results_jamming = experiment.run_pair_of_simulations(
			schedule_generation_funciton_honest,
			schedule_generation_funciton_jamming,
			args.upfront_base_coeff_range,
			args.upfront_rate_coeff_range,
			attackers_nodes=("Alice", "Dave"))

		return results_honest, results_jamming

	def run_wheel_experiments():
		with open(WHEEL_SNAPSHOT_FILENAME, 'r') as snapshot_file:
			snapshot_json = json.load(snapshot_file)

		ln_model = LNModel(snapshot_json, args.default_num_slots)
		ln_model.set_fee_for_all(
			RevenueType.SUCCESS,
			args.success_base_fee,
			args.success_fee_rate)

		experiment = Experiment(
			ln_model,
			simulator,
			args.num_runs_per_simulation)

		def schedule_generation_funciton_honest():
			return generate_honest_schedule(
				senders_list=("Alice", "Bob", "Charlie", "Dave"),
				receivers_list=("Alice", "Bob", "Charlie", "Dave"),
				duration=args.simulation_duration,
				must_route_via=["Hub"])

		def schedule_generation_funciton_jamming():
			return generate_jamming_schedule(
				sender="JammerSender",
				receiver="JammerReceiver",
				duration=args.simulation_duration,
				must_route_via=["Alice", "Hub", "Bob", "Charlie", "Hub", "Dave"])

		results_honest, results_jamming = experiment.run_pair_of_simulations(
			schedule_generation_funciton_honest,
			schedule_generation_funciton_jamming,
			args.upfront_base_coeff_range,
			args.upfront_rate_coeff_range,
			attackers_nodes=("JammerSender", "JammerReceiver"))
		return results_honest, results_jamming

	start_timestamp = int(time())
	if args.scenario == "abcd":
		results_honest, results_jamming = run_linear_experiments()
	elif args.scenario == "wheel":
		results_honest, results_jamming = run_wheel_experiments()
	end_timestamp = int(time())

	results = {
		"params": {
			"scenario": args.scenario,
			"simulation_duration": args.simulation_duration,
			"num_runs_per_simulation": args.num_runs_per_simulation,
			"success_base_fee": args.success_base_fee,
			"success_fee_rate": args.success_fee_rate,
			"no_balance_failures": args.no_balance_failures,
			"keep_receiver_upfront_fee": args.keep_receiver_upfront_fee,
			"default_num_slots": args.default_num_slots,
			"max_num_attempts_per_route_honest": args.max_num_attempts_honest,
			"max_num_attempts_per_route_jamming": args.max_num_attempts_jamming,
			"dust_limit": ProtocolParams["DUST_LIMIT"],
			"honest_payment_every_seconds": PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"],
			"min_processing_delay": PaymentFlowParams["MIN_DELAY"],
			"expected_extra_processing_delay": PaymentFlowParams["EXPECTED_EXTRA_DELAY"],
			"jam_delay": PaymentFlowParams["JAM_DELAY"]
		},
		"simulations": {
			"honest": sorted(
				results_honest,
				key=lambda d: (d["upfront_base_coeff"], d["upfront_rate_coeff"]),
				reverse=False),
			"jamming": sorted(
				results_jamming,
				key=lambda d: (d["upfront_base_coeff"], d["upfront_rate_coeff"]),
				reverse=False)
		}
	}

	running_time = end_timestamp - start_timestamp
	results_to_json_file(results, end_timestamp)
	results_to_csv_file(results, end_timestamp)
	print("\nRunning time (min):", round(running_time / 60, 1))


def results_to_json_file(results, timestamp):
	'''
		Dump the results into a JSON file.
	'''
	with open("results/" + str(timestamp) + "-results" + ".json", "w", newline="") as f:
		json.dump(results, f, indent=4)


def results_to_csv_file(results, timestamp):
	'''
		Dump the results into a CSV file.
	'''
	# get all nodes names from some simulation result to avoid passing ln_graph here as a parameter
	nodes = sorted([node for node in next(iter(results["simulations"]["honest"]))["revenues"]])
	with open("results/" + str(timestamp) + "-results" + ".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter=",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		for simulation_type in results["simulations"]:
			revenue_titles = [node[:1] + "_" + simulation_type[:1] + "_" + "revenue" for node in nodes]
			writer.writerow([
				"upfront_base_coeff",
				"upfront_rate_coeff",
				"sent",
				"failed",
				"reached_receiver"]
				+ revenue_titles)
			for result in results["simulations"][simulation_type]:
				revenues = [result["revenues"][node] for node in nodes]
				writer.writerow([
					result["upfront_base_coeff"],
					result["upfront_rate_coeff"],
					result["stats"]["num_sent"],
					result["stats"]["num_failed"],
					result["stats"]["num_reached_receiver"]]
					+ revenues)
			writer.writerow("")
		for param_name in results["params"]:
			writer.writerow([param_name, results["params"][param_name]])


if __name__ == "__main__":
	main()

import argparse
from time import time
from random import seed
import sys
import csv

from params import FeeParams, ProtocolParams, PaymentFlowParams
from scenario import Scenario

import logging
logger = logging.getLogger(__name__)


DEFAULT_UPFRONT_BASE_COEFF_RANGE = [n / 10000 for n in range(10 + 1)]
DEFAULT_UPFRONT_RATE_COEFF_RANGE = [0]


ABCD_SNAPSHOT_FILENAME = "./snapshots/listchannels_abcd.json"
WHEEL_SNAPSHOT_FILENAME = "./snapshots/listchannels_wheel.json"
REAL_SNAPSHOT_FILENAME = "./snapshots/listchannels-2021-12-09.json"
VIRTUAL_SNAPSHOT_FILENAME = "./snapshots/small-node-0263a6.json"


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--scenario",
		type=str,
		choices={"abcd", "wheel-hardcoded-route", "wheel", "wheel-long-routes", "real", "virtual"},
		help="LN graph JSON filename."
	)
	parser.add_argument(
		"--duration",
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
		"--default_num_slots_per_channel_in_direction",
		default=ProtocolParams["NUM_SLOTS"],
		type=int,
		help="Number of slots for honest channels (attackes has twice as many)."
	)
	parser.add_argument(
		"--max_num_attempts_honest",
		default=3,
		type=int,
		help="Number of attempts per honest payment in case of balance or deliberate failures."
	)
	parser.add_argument(
		"--max_num_attempts_jamming",
		default=ProtocolParams["NUM_SLOTS"] + 10,
		type=int,
		help="Number of attempts per jam payment in case of balance or deliberate failures."
	)
	parser.add_argument(
		"--max_num_routes_honest",
		default=10,
		type=int,
		help="Number of different routes per honest payment."
	)
	parser.add_argument(
		"--max_num_routes_jamming",
		default=None,
		type=int,
		help="Number of different routes per jam. By default, we try all routes until all target node pairs are jammed."
	)
	parser.add_argument(
		"--no_balance_failures",
		dest="no_balance_failures",
		default=False,
		action="store_true",
		help="Never fail payments because of low capacity."
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
		"--target_channel_capacity",
		default=None,
		type=int,
		help="Capacity of a target channel, in single-channel simulations."
	)
	parser.add_argument(
		"--honest_payments_per_second",
		default=PaymentFlowParams["HONEST_PAYMENTS_PER_SECOND"],
		type=float,
		help="Honest payment flow (default is set in params)."
	)
	parser.add_argument(
		"--num_jamming_batches",
		default=None,
		type=int,
		help="Num jamming batches to extrapolate from."
	)
	parser.add_argument(
		"--num_target_node_pairs",
		default=None,
		type=int,
		help="The number of target node pairs to pick (adjacent to the target node)."
	)
	parser.add_argument(
		"--max_target_node_pairs_per_route",
		default=ProtocolParams["MAX_ROUTE_LENGTH"] - 3,
		type=int,
		help="The number of target node pairs to try to include into jammer's routes."
	)
	parser.add_argument(
		"--max_route_length",
		default=ProtocolParams["MAX_ROUTE_LENGTH"],
		type=int,
		help="The maximal route length (number of nodes)."
	)
	parser.add_argument(
		"--extrapolate_jamming_revenues",
		dest="extrapolate_jamming_revenues",
		default=False,
		action="store_true",
		help="Extrapolate revenue in jamming experiment from just one set of upfront coeffieicnts."
	)
	parser.add_argument(
		"--compact_output",
		dest="compact_output",
		default=False,
		action="store_true",
		help="Only store revenues of the target node (must be present) and the jammer's nodes."
	)
	parser.add_argument(
		"--seed",
		type=int,
		help="Seed for randomness initialization."
	)
	parser.add_argument(
		"--log_level",
		type=str,
		choices={"critical", "error", "warning", "info", "debug"},
		default="info",
		help="Seed for randomness initialization."
	)
	args = parser.parse_args()

	start_timestamp = int(time())
	log_levels = {
		"critical": logging.CRITICAL,
		"error": logging.ERROR,
		"warn": logging.WARNING,
		"warning": logging.WARNING,
		"info": logging.INFO,
		"debug": logging.DEBUG
	}

	initialize_logging(start_timestamp, log_levels[args.log_level])

	if args.seed is not None:
		logger.debug(f"Initializing randomness seed: {args.seed}")
		seed(args.seed)

	if args.scenario == "abcd":
		scenario = Scenario(
			scenario_name=args.scenario,
			snapshot_filename=ABCD_SNAPSHOT_FILENAME,
			honest_senders=["Alice"],
			honest_receivers=["Dave"],
			target_node_pairs=[("Bob", "Charlie")],
			honest_must_route_via_nodes=["Bob", "Charlie"],
			jammer_must_route_via_nodes=["Bob", "Charlie"])
	elif args.scenario == "wheel-hardcoded-route":
		scenario = Scenario(
			scenario_name=args.scenario,
			snapshot_filename=WHEEL_SNAPSHOT_FILENAME,
			honest_senders=["Alice", "Charlie"],
			honest_receivers=["Bob", "Dave"],
			target_node_pairs=[("Alice", "Hub"), ("Hub", "Bob"), ("Charlie", "Hub"), ("Hub", "Dave")],
			jammer_sends_to_nodes=["Alice"],
			jammer_receives_from_nodes=["Dave"],
			honest_must_route_via_nodes=["Hub"],
			jammer_must_route_via_nodes=["Alice", "Hub", "Bob", "Charlie", "Hub", "Dave"])
	elif args.scenario == "wheel":
		scenario = Scenario(
			scenario_name=args.scenario,
			snapshot_filename=WHEEL_SNAPSHOT_FILENAME,
			honest_senders=["Alice", "Charlie"],
			honest_receivers=["Bob", "Dave"],
			target_node="Hub",
			honest_must_route_via_nodes=["Hub"])
	elif args.scenario == "real":
		#big_node = "030c3f19d742ca294a55c00376b3b355c3c90d61c6b6b39554dbc7ac19b141c14f"
		#medium_node = "02ad6fb8d693dc1e4569bcedefadf5f72a931ae027dc0f0c544b34c1c6f3b9a02b"
		small_node = "0263a6d2f0fed7b1e14d01a0c6a6a1c0fae6e0907c0ac415574091e7839a00405b"
		target_node = small_node
		scenario = Scenario(
			scenario_name=args.scenario,
			snapshot_filename=REAL_SNAPSHOT_FILENAME,
			target_node=target_node,
			num_target_node_pairs=args.num_target_node_pairs,
			honest_must_route_via_nodes=[target_node])
	elif args.scenario == "virtual":
		# a real target node with neighbors plus a "virtual" node representing the LN as a whole
		# the LN virtual node connects to every other node
		small_node = "0263a6d2f0fed7b1e14d01a0c6a6a1c0fae6e0907c0ac415574091e7839a00405b"
		target_node = small_node
		neighbors = (
			"034502648ec5f4c673830e33984e72a03185f9df6758977fc3c67fade393d400e5",
			"03e5589e3801586ada3515728c4602716b62f0a50ca59f1b348a6c846d55eee4a5",
			"0391b71b1e30cce2f0e25dbe4ce848c19e159d1677a8368d1eb3e50a34d14f74f4",
			"029b17d9d393bb0a7db2cf14f96309b01e764f0553a5a50791e6d55202d9279191",
			"024a8228d764091fce2ed67e1a7404f83e38ea3c7cb42030a2789e73cf3b341365"
		)
		target_node_pairs = [(target_node, n) for n in neighbors] + [(n, target_node) for n in neighbors]
		scenario = Scenario(
			scenario_name=args.scenario,
			snapshot_filename=VIRTUAL_SNAPSHOT_FILENAME,
			honest_senders=neighbors,
			honest_receivers=neighbors,
			target_node=target_node,
			target_node_pairs=target_node_pairs,
			num_target_node_pairs=args.num_target_node_pairs,
			honest_must_route_via_nodes=[target_node])

	# Actually run the simulations
	if args.scenario in ("real", "virtual"):
		target_channel_capacity_range = [None]
	else:
		M = 1000 * 1000
		target_channel_capacity_range = [int(n * M) for n in [0.1, 0.2, 0.5, 1, 2, 5, 10]]
	# doesn't matter for ABCD, runs fast enough for real graph (??)
	max_route_length = 14
	#max_target_node_pairs_per_route = 10
	honest_payments_per_second = 1
	upfront_base_coeff_range = [n / 100000 for n in range(100, 500 + 1)]
	breakeven_upfront_coeffs = []
	scenario_num, total_num_scenarios = 0, len(target_channel_capacity_range)
	logger.info(f"Target capacities: {target_channel_capacity_range}")
	logger.info(f"Upfront base coeff range: {upfront_base_coeff_range}")
	logger.info(f"Total scenarios: {total_num_scenarios}")
	for target_channel_capacity in target_channel_capacity_range:
		scenario_num += 1
		percent_done = round(100 * scenario_num / total_num_scenarios)
		logger.info(f"Simulating scenario {scenario_num} / {total_num_scenarios} ({percent_done} % done)")
		logger.info(f"Target channel capacity: {target_channel_capacity}, honest payments per second: {honest_payments_per_second}")
		breakeven_upfront_base_coeff, _ = scenario.run(
			duration=args.duration,
			num_jamming_batches=args.num_jamming_batches,
			upfront_base_coeff_range=upfront_base_coeff_range,
			upfront_rate_coeff_range=args.upfront_rate_coeff_range,
			max_num_attempts_per_route_honest=args.max_num_attempts_honest,
			max_num_attempts_per_route_jamming=args.max_num_attempts_jamming,
			max_num_routes_honest=args.max_num_routes_honest,
			num_runs_per_simulation=args.num_runs_per_simulation,
			max_target_node_pairs_per_route=len(target_node_pairs),
			max_route_length=max_route_length,
			honest_payments_per_second=honest_payments_per_second,
			target_channel_capacity=target_channel_capacity,
			compact_output=(args.scenario == "real"),
			extrapolate_jamming_revenues=args.extrapolate_jamming_revenues)
		breakeven_upfront_coeffs.append((target_channel_capacity, breakeven_upfront_base_coeff))
		scenario.results_to_json_file(start_timestamp + scenario_num)
		scenario.results_to_csv_file(start_timestamp + scenario_num)

	end_timestamp = int(time())
	running_time = end_timestamp - start_timestamp
	logger.info(f"Breakeven upfront base coeffs: {breakeven_upfront_coeffs}")
	with open("results/" + str(start_timestamp + scenario_num + 1) + "-breakeven" + ".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter=",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["target_channel_capacity", "breakeven_upfront_base_coeff"])
		writer.writerows(breakeven_upfront_coeffs)
		writer.writerow("")
		writer.writerow(["honest_payments_per_second", honest_payments_per_second])
		writer.writerow(["duration", args.duration])
	logger.info(f"Running time (min): {round(running_time / 60, 1)}")


def initialize_logging(start_timestamp, log_level):
	LOG_FILENAME = "results/" + str(start_timestamp) + "-log.txt"
	#logging.basicConfig(filename=LOG_FILENAME, filemode="w", level=logging.DEBUG)
	root_logger = logging.getLogger()
	root_logger.setLevel(log_level)
	format_string = "%(asctime)s: [%(levelname)s] %(name)s: %(message)s"
	# Console output
	root_logger.handler = logging.StreamHandler(sys.stdout)
	formatter = logging.Formatter(format_string)
	root_logger.handler.setFormatter(formatter)
	root_logger.addHandler(root_logger.handler)
	# File output
	fh = logging.FileHandler(LOG_FILENAME)
	fh.setFormatter(logging.Formatter(format_string))
	root_logger.addHandler(fh)


if __name__ == "__main__":
	main()

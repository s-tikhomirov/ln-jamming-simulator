import argparse
from time import time
from random import seed
import sys

from params import FeeParams, ProtocolParams
from scenario import Scenario

import logging
logger = logging.getLogger(__name__)


DEFAULT_UPFRONT_BASE_COEFF_RANGE = [0, 0.001, 0.01]
DEFAULT_UPFRONT_RATE_COEFF_RANGE = [0, 0.1, 0.5]

ABCD_SNAPSHOT_FILENAME = "./snapshots/listchannels_abcd.json"
WHEEL_SNAPSHOT_FILENAME = "./snapshots/listchannels_wheel.json"
REAL_SNAPSHOT_FILENAME = "./snapshots/listchannels-2021-12-09.json"


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--scenario",
		type=str,
		choices={"abcd", "wheel-hardcoded-route", "wheel", "wheel-long-routes", "real"},
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
		default=1,
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
		help="Number of different routes per jam. By default, we try all routes until all target hops are jammed."
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

	if args.scenario in ("abcd", "wheel-hardcoded-route", "wheel"):
		if args.scenario == "abcd":
			scenario = Scenario(
				scenario_name=args.scenario,
				snapshot_filename=ABCD_SNAPSHOT_FILENAME,
				honest_senders=["Alice"],
				honest_receivers=["Dave"],
				target_hops=[("Bob", "Charlie")])
		elif args.scenario == "wheel-hardcoded-route":
			scenario = Scenario(
				scenario_name=args.scenario,
				snapshot_filename=WHEEL_SNAPSHOT_FILENAME,
				honest_senders=["Alice", "Charlie"],
				honest_receivers=["Bob", "Dave"],
				target_hops=[("Alice", "Hub"), ("Hub", "Bob"), ("Charlie", "Hub"), ("Hub", "Dave")],
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
		scenario.run(
			duration=args.duration,
			upfront_base_coeff_range=args.upfront_base_coeff_range,
			upfront_rate_coeff_range=args.upfront_rate_coeff_range,
			max_num_attempts_per_route_honest=args.max_num_attempts_honest,
			max_num_attempts_per_route_jamming=args.max_num_attempts_jamming,
			max_num_routes_honest=args.max_num_routes_honest,
			num_runs_per_simulation=args.num_runs_per_simulation,
			max_target_hops_per_route=ProtocolParams["MAX_ROUTE_LENGTH"] - 2,
			max_route_length=ProtocolParams["MAX_ROUTE_LENGTH"])
	elif args.scenario == "real":
		#big_node = "02ad6fb8d693dc1e4569bcedefadf5f72a931ae027dc0f0c544b34c1c6f3b9a02b"
		small_node = "0263a6d2f0fed7b1e14d01a0c6a6a1c0fae6e0907c0ac415574091e7839a00405b"
		target_node = small_node
		scenario = Scenario(
			scenario_name=args.scenario,
			snapshot_filename=REAL_SNAPSHOT_FILENAME,
			target_node=target_node,
			honest_must_route_via_nodes=[target_node])
		scenario.run(
			duration=args.duration,
			num_jamming_batches_to_extrapolate_from=3,
			upfront_base_coeff_range=args.upfront_base_coeff_range,
			upfront_rate_coeff_range=args.upfront_rate_coeff_range,
			max_num_attempts_per_route_honest=args.max_num_attempts_honest,
			max_num_attempts_per_route_jamming=args.max_num_attempts_jamming,
			max_num_routes_honest=args.max_num_routes_honest,
			num_runs_per_simulation=args.num_runs_per_simulation,
			max_target_hops_per_route=7,
			max_route_length=10,
			compact_output=True)
	else:
		logger.error(f"Not yet properly implemented for scenario {args.scenario}!")
		exit()

	end_timestamp = int(time())
	running_time = end_timestamp - start_timestamp
	scenario.results_to_json_file(start_timestamp)
	scenario.results_to_csv_file(start_timestamp)
	logger.info(f"Running time (min): {round(running_time / 60, 1)}")


def initialize_logging(start_timestamp, log_level):
	LOG_FILENAME = "results/" + str(start_timestamp) + "-log.txt"
	#logging.basicConfig(filename=LOG_FILENAME, filemode="w", level=logging.DEBUG)
	root_logger = logging.getLogger()
	root_logger.setLevel(log_level)
	format_string = "[%(levelname)s] %(name)s: %(message)s"
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

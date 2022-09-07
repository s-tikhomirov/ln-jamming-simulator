import argparse
from time import time
from random import seed
import json
import csv
import sys

from params import FeeParams, ProtocolParams, PaymentFlowParams
from lnmodel import LNModel
from enumtypes import FeeType
from simulator import Simulator
from schedule import HonestSchedule, JammingSchedule

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

	def get_compact_output(results, relevant_nodes):
		from copy import deepcopy
		results_compact = deepcopy(results)
		for i, result in enumerate(results):
			# sic: we can't modify a JSON while iterating through it
			# hence, we iterate through the original results
			# and delete the unnecessary elements in the compact results
			for node in result["revenues"]:
				if node not in relevant_nodes:
					del results_compact[i]["revenues"][node]
		return results_compact

	def run_scenario(
		snapshot_filename,
		honest_senders=None,
		honest_receivers=None,
		target_node=None,
		target_hops=None,
		jammer_sends_to_nodes=None,
		jammer_receives_from_nodes=None,
		honest_must_route_via_nodes=[],
		jammer_must_route_via_nodes=[],
		max_target_hops_per_route=ProtocolParams["MAX_ROUTE_LENGTH"] - 2,
		max_route_length=ProtocolParams["MAX_ROUTE_LENGTH"],
		compact_output=False):

		with open(snapshot_filename, 'r') as snapshot_file:
			snapshot_json = json.load(snapshot_file)
		ln_model = LNModel(
			snapshot_json,
			args.default_num_slots_per_channel_in_direction,
			args.no_balance_failures)

		# set honest senders and receivers
		assert((honest_senders is None) == (honest_receivers is None))
		if honest_senders is None and honest_receivers is None:
			if target_node is None:
				logger.critical("Honest senders / receivers are not specified, but target not is also not specified!")
				exit()
			honest_senders = list(set(hop[0] for hop in ln_model.routing_graph.in_edges(target_node)))
			honest_receivers = list(set(hop[1] for hop in ln_model.routing_graph.out_edges(target_node)))
			if not (honest_senders and honest_receivers):
				if not honest_senders:
					logger.critical(f"Target node {target_node} has no incoming edges")
				if not honest_receivers:
					logger.critical(f"Target node {target_node} has no outgoing edges")
				logger.critical(f"We can't simulate honest payment flow!")
				exit()
			assert(honest_senders and honest_receivers)
			logger.info(f"Setting honest senders / receiver to incoming / outgoing edges of target node {target_node}")
			logger.info(f"Set {len(honest_senders)} honest senders")
			logger.debug(f"{honest_senders}")
			logger.info(f"Set {len(honest_receivers)} honest senders")
			logger.debug(f"{honest_receivers}")

		# set target hops
		if target_hops is not None:
			# if given, target hops override target node
			pass
		elif target_node is not None:
			in_edges = list(ln_model.routing_graph.in_edges(target_node, data=False))
			out_edges = list(ln_model.routing_graph.out_edges(target_node, data=False))
			#target_hops = in_edges[:5] + out_edges[:5]
			target_hops = in_edges + out_edges
		else:
			logger.critical(f"Neither target hops nor target nodes are specified!")
			exit()
		logger.info(f"Set {len(target_hops)} target hops")
		logger.debug(f":{target_hops}")

		# open jammer's channels
		assert((jammer_sends_to_nodes is None) == (jammer_receives_from_nodes is None))
		jammer_opens_channels_to_all_targets = jammer_sends_to_nodes is None
		jammer_num_slots = len(target_hops) * (args.default_num_slots_per_channel_in_direction + 1)
		if jammer_opens_channels_to_all_targets:
			logger.info(f"Jammer opens channels to and from all target hops")
			jammer_sends_to = [hop[0] for hop in target_hops]
			jammer_receives_from = [hop[1] for hop in target_hops]
		else:
			logger.info(f"Jammer opens channels to {jammer_sends_to_nodes} and from {jammer_receives_from_nodes}")
			jammer_sends_to = jammer_sends_to_nodes
			jammer_receives_from = jammer_receives_from_nodes
		ln_model.add_jammers_channels(
			send_to_nodes=jammer_sends_to,
			receive_from_nodes=jammer_receives_from,
			num_slots=jammer_num_slots)

		# FIXME: don't set fee for real experiment!
		ln_model.set_fee_for_all(
			FeeType.SUCCESS,
			args.success_base_fee,
			args.success_fee_rate)

		simulator = Simulator(
			ln_model,
			target_hops,
			max_num_attempts_per_route_honest=args.max_num_attempts_honest,
			max_num_attempts_per_route_jamming=args.max_num_attempts_jamming,
			max_num_routes_honest=args.max_num_routes_honest,
			num_runs_per_simulation=args.num_runs_per_simulation,
			jammer_must_route_via_nodes=jammer_must_route_via_nodes,
			max_target_hops_per_route=max_target_hops_per_route,
			max_route_length=max_route_length)

		logger.info("Starting jamming simulations")

		def schedule_generation_function_jamming():
			j_sch = JammingSchedule(end_time=args.simulation_duration)
			return j_sch

		results_jamming = simulator.run_simulation_series(
			schedule_generation_function_jamming,
			args.upfront_base_coeff_range,
			args.upfront_rate_coeff_range)

		logger.info("Starting honest simulations")

		def schedule_generation_function_honest():
			h_sch = HonestSchedule(
				end_time=args.simulation_duration,
				senders=honest_senders,
				receivers=honest_receivers,
				must_route_via_nodes=honest_must_route_via_nodes)
			return h_sch

		results_honest = simulator.run_simulation_series(
			schedule_generation_function_honest,
			args.upfront_base_coeff_range,
			args.upfront_rate_coeff_range)

		if compact_output:
			assert(target_node is not None)
			relevant_nodes = [target_node, "JammerSender", "JammerReceiver"]
			results_jamming = get_compact_output(results_jamming, relevant_nodes)
			results_honest = get_compact_output(results_honest, relevant_nodes)

		results = {
			"params": {
				"scenario": args.scenario,
				"target_node": target_node,
				"num_target_hops": len(target_hops),
				"simulation_duration": args.simulation_duration,
				"num_runs_per_simulation": args.num_runs_per_simulation,
				"success_base_fee": args.success_base_fee,
				"success_fee_rate": args.success_fee_rate,
				"no_balance_failures": args.no_balance_failures,
				"default_num_slots_per_channel_in_direction": args.default_num_slots_per_channel_in_direction,
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
		return results

	if args.scenario == "abcd":
		results = run_scenario(
			snapshot_filename=ABCD_SNAPSHOT_FILENAME,
			honest_senders=["Alice"],
			honest_receivers=["Dave"],
			target_hops=[("Bob", "Charlie")])
	elif args.scenario == "wheel-hardcoded-route":
		results = run_scenario(
			snapshot_filename=WHEEL_SNAPSHOT_FILENAME,
			honest_senders=["Alice", "Charlie"],
			honest_receivers=["Bob", "Dave"],
			target_hops=[("Alice", "Hub"), ("Hub", "Bob"), ("Charlie", "Hub"), ("Hub", "Dave")],
			jammer_sends_to_nodes=["Alice"],
			jammer_receives_from_nodes=["Dave"],
			honest_must_route_via_nodes=["Hub"],
			jammer_must_route_via_nodes=["Alice", "Hub", "Bob", "Charlie", "Hub", "Dave"])
	elif args.scenario == "wheel":
		results = run_scenario(
			snapshot_filename=WHEEL_SNAPSHOT_FILENAME,
			honest_senders=["Alice", "Charlie"],
			honest_receivers=["Bob", "Dave"],
			target_node="Hub",
			honest_must_route_via_nodes=["Hub"])
	elif args.scenario == "real":
		#big_node = "02ad6fb8d693dc1e4569bcedefadf5f72a931ae027dc0f0c544b34c1c6f3b9a02b"
		small_node = "0263a6d2f0fed7b1e14d01a0c6a6a1c0fae6e0907c0ac415574091e7839a00405b"
		target_node = small_node
		results = run_scenario(
			snapshot_filename=REAL_SNAPSHOT_FILENAME,
			target_node=target_node,
			honest_must_route_via_nodes=[target_node],
			max_target_hops_per_route=7,
			max_route_length=10,
			compact_output=True)
	else:
		logger.error(f"Not yet properly implemented for scenario {args.scenario}!")
		exit()

	end_timestamp = int(time())
	running_time = end_timestamp - start_timestamp
	results_to_json_file(results, start_timestamp)
	results_to_csv_file(results, start_timestamp)
	logger.info(f"Running time (min): {round(running_time / 60, 1)}")


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
			revenue_titles = [simulation_type[:1] + "_" + node[:7] for node in nodes]
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

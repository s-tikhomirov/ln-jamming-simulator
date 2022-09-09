import json
import csv

from params import FeeParams, ProtocolParams, PaymentFlowParams
from lnmodel import LNModel
from enumtypes import FeeType
from simulator import Simulator
from schedule import HonestSchedule, JammingSchedule

import logging
logger = logging.getLogger(__name__)


class Scenario:

	def __init__(
		self,
		scenario_name,
		snapshot_filename,
		default_num_slots_per_channel_in_direction=ProtocolParams["NUM_SLOTS"],
		no_balance_failures=False,
		set_default_success_fee=True,
		default_success_base_fee=FeeParams["SUCCESS_BASE"],
		default_success_fee_rate=FeeParams["SUCCESS_RATE"],
		honest_senders=None,
		honest_receivers=None,
		target_node=None,
		target_hops=None,
		jammer_sends_to_nodes=None,
		jammer_receives_from_nodes=None,
		honest_must_route_via_nodes=[],
		jammer_must_route_via_nodes=[]):

		self.scenario_name = scenario_name
		self.default_success_base_fee = default_success_base_fee
		self.default_success_fee_rate = default_success_fee_rate
		self.no_balance_failures = no_balance_failures
		self.set_default_success_fee = set_default_success_fee
		self.honest_must_route_via_nodes = honest_must_route_via_nodes
		self.jammer_must_route_via_nodes = jammer_must_route_via_nodes
		self.default_num_slots_per_channel_in_direction = default_num_slots_per_channel_in_direction

		with open(snapshot_filename, 'r') as snapshot_file:
			snapshot_json = json.load(snapshot_file)

		self.ln_model = LNModel(
			snapshot_json,
			default_num_slots_per_channel_in_direction,
			no_balance_failures)

		# set honest senders and receivers
		assert (honest_senders is None) == (honest_receivers is None)
		if honest_senders is None and honest_receivers is None:
			if target_node is None:
				logger.critical("Honest senders / receivers are not specified, but target not is also not specified!")
				exit()
			honest_senders = list(set(hop[0] for hop in self.ln_model.routing_graph.in_edges(target_node)))
			honest_receivers = list(set(hop[1] for hop in self.ln_model.routing_graph.out_edges(target_node)))
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

		self.honest_senders = honest_senders
		self.honest_receivers = honest_receivers
		self.target_node = target_node
		self.target_hops = self.get_target_hops(target_node, target_hops)

		assert (jammer_sends_to_nodes is None) == (jammer_receives_from_nodes is None)
		jammer_opens_channels_to_all_targets = jammer_sends_to_nodes is None
		jammer_num_slots = len(self.target_hops) * (default_num_slots_per_channel_in_direction + 1)
		if jammer_opens_channels_to_all_targets:
			logger.info(f"Jammer opens channels to and from all target hops")
			jammer_sends_to = [hop[0] for hop in self.target_hops]
			jammer_receives_from = [hop[1] for hop in self.target_hops]
		else:
			logger.info(f"Jammer opens channels to {jammer_sends_to_nodes} and from {jammer_receives_from_nodes}")
			jammer_sends_to = jammer_sends_to_nodes
			jammer_receives_from = jammer_receives_from_nodes
		self.ln_model.add_jammers_channels(
			send_to_nodes=jammer_sends_to,
			receive_from_nodes=jammer_receives_from,
			num_slots=jammer_num_slots)

		# FIXME: don't set fee for real experiment!
		if self.set_default_success_fee:
			self.ln_model.set_fee_for_all(FeeType.SUCCESS, default_success_base_fee, default_success_fee_rate)

	def get_target_hops(self, target_node=None, target_hops=None):
		if target_hops is not None:
			# TODO: assert all target hops are in graph
			target_hops = target_hops
		elif target_node is not None:
			in_edges = list(self.ln_model.routing_graph.in_edges(target_node, data=False))
			out_edges = list(self.ln_model.routing_graph.out_edges(target_node, data=False))
			#target_hops = in_edges[:5] + out_edges[:5]
			target_hops = in_edges + out_edges
		else:
			logger.critical(f"Neither target hops nor target nodes are specified!")
			exit()
		logger.info(f"Set {len(target_hops)} target hops")
		logger.debug(f":{target_hops}")
		return target_hops

	def run(
		self,
		duration,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		max_num_attempts_per_route_honest,
		max_num_attempts_per_route_jamming,
		max_num_routes_honest,
		num_runs_per_simulation,
		max_target_hops_per_route,
		max_route_length,
		num_jamming_batches_to_extrapolate_from=None,
		compact_output=False):

		simulator = Simulator(
			ln_model=self.ln_model,
			target_hops=self.target_hops,
			max_num_attempts_per_route_honest=max_num_attempts_per_route_honest,
			max_num_attempts_per_route_jamming=max_num_attempts_per_route_jamming,
			max_num_routes_honest=max_num_routes_honest,
			num_runs_per_simulation=num_runs_per_simulation,
			jammer_must_route_via_nodes=self.jammer_must_route_via_nodes,
			max_target_hops_per_route=max_target_hops_per_route,
			max_route_length=max_route_length)

		logger.info("Starting jamming simulations")
		if num_jamming_batches_to_extrapolate_from is not None:
			# first batch at time 0, last batch at time (num_batches - 1) * jam_delay
			jamming_duration = (num_jamming_batches_to_extrapolate_from - 1) * PaymentFlowParams["JAM_DELAY"]
			logger.info(f"Extrapolating jamming results from {num_jamming_batches_to_extrapolate_from} batches (duration {jamming_duration})")
		else:
			jamming_duration = duration

		results_jamming = simulator.run_simulation_series(
			schedule_generation_function=(
				lambda duration: JammingSchedule(duration=duration)),
			duration=jamming_duration,
			upfront_base_coeff_range=upfront_base_coeff_range,
			upfront_rate_coeff_range=upfront_rate_coeff_range,
			normalize_results_for_duration=True)

		logger.info("Starting honest simulations")

		results_honest = simulator.run_simulation_series(
			schedule_generation_function=(
				lambda duration: HonestSchedule(
					duration=duration,
					senders=self.honest_senders,
					receivers=self.honest_receivers,
					must_route_via_nodes=self.honest_must_route_via_nodes)),
			duration=duration,
			upfront_base_coeff_range=upfront_base_coeff_range,
			upfront_rate_coeff_range=upfront_rate_coeff_range,
			normalize_results_for_duration=True)

		if compact_output:
			assert self.target_node is not None
			relevant_nodes = [self.target_node, "JammerSender", "JammerReceiver"]
			results_jamming = Scenario.get_compact_output(results_jamming, relevant_nodes)
			results_honest = Scenario.get_compact_output(results_honest, relevant_nodes)

		results = {
			"params": {
				"scenario": self.scenario_name,
				"target_node": self.target_node,
				"num_target_hops": len(self.target_hops),
				"duration": duration,
				"results_normalized": simulator.normalize_results_for_duration,
				"num_runs_per_simulation": num_runs_per_simulation,
				"set_default_success_fee": self.set_default_success_fee,
				"default_success_base_fee": self.default_success_base_fee,
				"default_success_fee_rate": self.default_success_fee_rate,
				"no_balance_failures": self.no_balance_failures,
				"default_num_slots_per_channel_in_direction": self.default_num_slots_per_channel_in_direction,
				"max_num_attempts_per_route_honest": max_num_attempts_per_route_honest,
				"max_num_attempts_per_route_jamming": max_num_attempts_per_route_jamming,
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
		self.results = results

	@staticmethod
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

	def results_to_json_file(self, timestamp):
		'''
			Dump the results into a JSON file.
		'''
		with open("results/" + str(timestamp) + "-results" + ".json", "w", newline="") as f:
			json.dump(self.results, f, indent=4)

	def results_to_csv_file(self, timestamp):
		'''
			Dump the results into a CSV file.
		'''
		# get all nodes names from some simulation result to avoid passing ln_graph here as a parameter
		nodes = sorted([node for node in next(iter(self.results["simulations"]["honest"]))["revenues"]])
		with open("results/" + str(timestamp) + "-results" + ".csv", "w", newline="") as f:
			writer = csv.writer(f, delimiter=",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
			for simulation_type in self.results["simulations"]:
				revenue_titles = [simulation_type[:1] + "_" + node[:7] for node in nodes]
				writer.writerow([
					"upfront_base_coeff",
					"upfront_rate_coeff",
					"sent",
					"failed",
					"reached_receiver"]
					+ revenue_titles)
				for result in self.results["simulations"][simulation_type]:
					revenues = [result["revenues"][node] for node in nodes]
					writer.writerow([
						result["upfront_base_coeff"],
						result["upfront_rate_coeff"],
						result["stats"]["num_sent"],
						result["stats"]["num_failed"],
						result["stats"]["num_reached_receiver"]]
						+ revenues)
				writer.writerow("")
			for param_name in self.results["params"]:
				writer.writerow([param_name, self.results["params"][param_name]])

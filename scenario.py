import json
import csv
from numpy.random import exponential
from random import sample

from params import FeeParams, ProtocolParams, PaymentFlowParams
from lnmodel import LNModel
from enumtypes import FeeType
from simulator import JammingSimulator, HonestSimulator
from schedule import HonestSchedule, JammingSchedule

import logging
logger = logging.getLogger(__name__)


class Scenario:
	'''
		A Scenario specifies all parameters of a simulation (honest and jamming).
	'''

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
		target_node_pairs=None,
		num_target_node_pairs=None,
		jammer_sends_to_nodes=None,
		jammer_receives_from_nodes=None,
		honest_must_route_via_nodes=[],
		jammer_must_route_via_nodes=[]):
		'''
			- scenario_name
				A human-readable name to be written into results files for reference.

			- snapshot_finename
				A filename of a JSON file describing LN topology (Core Lightning listchannels format).

			- default_num_slots_per_channel_in_direction
				The number of slots per channel per direction by default.

			- no_balance_failures
				If True, all payments go through if amount is lower than capacity.
				If False, payments fail with probability = amount / capacity.

			- set_default_success_fee
				If True, set success-case fee parameters to all channels to default values.

			- default_success_base_fee
				Default value for success-case base fee.

			- default_success_base_fee
				Default value for success-case fee rate.

			- honest_senders
				The set of nodes that send honest payments.

			- honest_receivers
				The set of nodes that receive honest payments.

			- target_node
				Target node for jamming. If provided, all its adjacent channels are being jammed.

			- target_node_pairs
				Target hops (node pairs) for jamming.

			- num_target_node_pairs
				The number of target hops (allows for small-scale simulations of a subset of channels of highly-connected nodes).

			- jammer_sends_to_nodes
				The set of entry nodes for the jammer.

			- jammer_receives_from_nodes
				The set of exit nodes for the jammer.

			- honest_must_route_via_nodes
				A list of nodes that all honest payments must route through.

			- jammer_must_route_via_nodes
				A list of nodes that all jams must route through.
		'''

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
		self.target_node_pairs = self.get_target_node_pairs(target_node, target_node_pairs, num_target_node_pairs)
		logger.info(f"{len(self.target_node_pairs)} target node pairs selected")

		assert (jammer_sends_to_nodes is None) == (jammer_receives_from_nodes is None)
		jammer_opens_channels_to_all_targets = jammer_sends_to_nodes is None
		jammer_num_slots = len(self.target_node_pairs) * (default_num_slots_per_channel_in_direction + 1)
		if jammer_opens_channels_to_all_targets:
			logger.info(f"Jammer opens channels to and from all target node pairs")
			jammer_sends_to = [hop[0] for hop in self.target_node_pairs]
			jammer_receives_from = [hop[1] for hop in self.target_node_pairs]
		else:
			logger.info(f"Jammer opens channels to {jammer_sends_to_nodes} and from {jammer_receives_from_nodes}")
			jammer_sends_to = jammer_sends_to_nodes
			jammer_receives_from = jammer_receives_from_nodes
		self.ln_model.add_jammers_channels(
			send_to_nodes=jammer_sends_to,
			receive_from_nodes=jammer_receives_from,
			num_slots=jammer_num_slots)

		if self.set_default_success_fee:
			self.ln_model.set_fee_for_all(FeeType.SUCCESS, default_success_base_fee, default_success_fee_rate)

	def get_target_node_pairs(self, target_node=None, target_node_pairs=None, num_target_node_pairs=None):
		if target_node_pairs is not None:
			# TODO: assert all target node pairs are in graph
			target_node_pairs = target_node_pairs
		elif target_node is not None:
			# note: we choose target node pairs, not hops
			# a bi-directional hop represents two node pairs (A, B) and (B, A)
			# we first extract all such pairs, then select from them
			rg = self.ln_model.routing_graph
			in_edges = list(rg.in_edges(target_node, data=False))
			out_edges = list(rg.out_edges(target_node, data=False))
			all_adjacent_edges = in_edges + out_edges
			logger.info(f"There are {len(all_adjacent_edges)} edges adjacent to target node {self.target_node}")
			if num_target_node_pairs is None:
				target_node_pairs = all_adjacent_edges
			else:
				if len(all_adjacent_edges) < num_target_node_pairs:
					logger.critical(f"Requested {num_target_node_pairs} adjacent to a node with only {len(all_adjacent_edges)} adjacent channels!")
					exit()
				else:
					target_node_pairs = sample(all_adjacent_edges, num_target_node_pairs)
		else:
			logger.critical(f"Neither target node pairs nor target nodes are specified!")
			exit()
		logger.info(f"Set {len(target_node_pairs)} target node pairs")
		logger.debug(f":{target_node_pairs}")
		return target_node_pairs

	def run(
		self,
		duration,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		max_num_attempts_per_route_honest,
		max_num_attempts_per_route_jamming,
		max_num_routes_honest,
		num_runs_per_simulation,
		max_target_node_pairs_per_route=None,
		max_route_length=None,
		honest_payments_per_second=PaymentFlowParams["HONEST_PAYMENTS_PER_SECOND"],
		target_channel_capacity=None,
		num_jamming_batches=None,
		compact_output=False,
		normalize_results_for_duration=True,
		extrapolate_jamming_revenues=False):
		'''
			- duration
				The simulation duration (seconds). Schedules will be generated with this as their end time.

			- upfront_base_coeff_range
				The list of values for the upfront base coefficient (multiply success-case base fee by this to get upfront base fee).

			- upfront_rate_coeff_range
				The list of values for the upfront rate coefficient (multiply success-case fee rate by this to get upfront fee rate).

			- max_num_attempts_per_route_honest
				The number of attempts per route if an honest payment fails due to balance.

			- max_num_attempts_per_route_jamming
				The number of attempts per route if a jam fails due to balance (unlikely).

			- max_num_routes_honest
				The maximum number of routes to try for an honest payment.

			- num_runs_per_simulation
				The number of simulation runs to average results across.

			- max_target_node_pairs_per_route
				The maximum number of target hops a jammer tries to jam within a single route.

			- max_route_length
				The maximum route length (number of nodes).

			- honest_payments_per_second
				Expected delay between honest payments.

			- target_channel_capacity
				The capacity of the target channel (for single channel-based simulations).

			- num_jamming_batches
				The number of jamming batches (if not given, it's derived from duration and jam delay).

			- compact_output
				Save output only for relevant nodes.

			- normalize_results_for_duration
				Normalize revenues w.r.t. duration (so that results reflect revenue per second).

			- extrapolate_jamming_revenues
				Extrapolate jamming results based on jam batch delay and fees.
		'''

		assert max_target_node_pairs_per_route is not None or max_route_length is not None
		# route length is the number of NODES in the route, which includes two Jammer's channels
		if max_route_length is None:
			# ideally, we want to cover all target node pairs
			# we don't mind if some hops repeat in route, but don't actively seek it
			# TODO: is this optimal?
			max_route_length = ProtocolParams["MAX_ROUTE_LENGTH"]
		if max_target_node_pairs_per_route is None:
			max_target_node_pairs_per_route = min(len(self.target_node_pairs), max_route_length - 4)
		#logger.debug(f"Including up to {max_target_node_pairs_per_route} target node pairs in routes of length up to {max_route_length}")
		assert max_target_node_pairs_per_route <= max_route_length - 3

		if target_channel_capacity is not None:
			logger.debug(f"Target channel capacity is given: {target_channel_capacity}")
			assert len(self.target_node_pairs) == 1, target_channel_capacity
			target_u_node, target_d_node = self.target_node_pairs[0]
			self.ln_model.set_capacity(target_u_node, target_d_node, target_channel_capacity)

		if num_jamming_batches is None:
			from math import ceil
			num_jamming_batches = ceil(duration / PaymentFlowParams["JAM_DELAY"])

		# first batch starts at time 0, last batch starts at time (num_batches - 1) * jam_delay
		jamming_schedule_duration = (num_jamming_batches - 1) * PaymentFlowParams["JAM_DELAY"]
		# we run the simulation up until num_batches * jam delay to let the last batch complete
		jamming_simulation_duration = num_jamming_batches * PaymentFlowParams["JAM_DELAY"]

		if extrapolate_jamming_revenues:
			logger.info(f"Extrapolating jamming results from one upfront coefficient")

		logger.info(f"Schedule duration: {jamming_schedule_duration}")
		logger.info(f"Simulation duration: {jamming_simulation_duration}")
		logger.info(f"Number of jamming batches: {num_jamming_batches}")
		logger.info(f"Starting jamming simulations with ranges: {upfront_base_coeff_range} {upfront_rate_coeff_range}")
		j_sim = JammingSimulator(
			ln_model=self.ln_model,
			max_num_routes=None,
			max_num_attempts_per_route=max_num_attempts_per_route_jamming,
			max_route_length=max_route_length,
			num_runs_per_simulation=1 if num_jamming_batches is not None else None,
			target_node_pairs=self.target_node_pairs,
			target_node=self.target_node,
			max_target_node_pairs_per_route=max_target_node_pairs_per_route,
			jammer_must_route_via_nodes=self.jammer_must_route_via_nodes)
		results_jamming = j_sim.run_simulation_series(
			schedule_generation_function=(
				lambda duration: JammingSchedule(duration=jamming_schedule_duration)),
			duration=jamming_simulation_duration,
			upfront_base_coeff_range=upfront_base_coeff_range,
			upfront_rate_coeff_range=upfront_rate_coeff_range,
			normalize_results_for_duration=normalize_results_for_duration,
			extrapolate_jamming_revenues=extrapolate_jamming_revenues)

		logger.info(f"Starting honest simulations with ranges: {upfront_base_coeff_range} {upfront_rate_coeff_range}")
		h_sim = HonestSimulator(
			ln_model=self.ln_model,
			max_num_routes=max_num_routes_honest,
			max_num_attempts_per_route=max_num_attempts_per_route_honest,
			max_route_length=max_route_length,
			num_runs_per_simulation=num_runs_per_simulation)
		results_honest = h_sim.run_simulation_series(
			schedule_generation_function=(
				lambda duration: HonestSchedule(
					duration=duration,
					senders=self.honest_senders,
					receivers=self.honest_receivers,
					payment_generation_delay_function=lambda: exponential(1 / honest_payments_per_second),
					must_route_via_nodes=self.honest_must_route_via_nodes)),
			duration=duration,
			upfront_base_coeff_range=upfront_base_coeff_range,
			upfront_rate_coeff_range=upfront_rate_coeff_range,
			normalize_results_for_duration=normalize_results_for_duration)

		if compact_output:
			assert self.target_node is not None
			relevant_nodes = [self.target_node, "JammerSender", "JammerReceiver"]
			results_jamming = Scenario.get_compact_output(results_jamming, relevant_nodes)
			results_honest = Scenario.get_compact_output(results_honest, relevant_nodes)

		if self.target_node is not None:
			target_nodes = [self.target_node]
		else:
			assert len(self.target_node_pairs) == 1
			target_nodes = list(self.target_node_pairs[0])
			logger.debug(f"Choosing ")
		logger.debug(f"Deciding breakeven based on revenues of target node {target_nodes}")
		breakeven_stats = Scenario.get_breakeven_stats(results_honest, results_jamming, target_nodes)

		results = {
			"params": {
				"scenario": self.scenario_name,
				"target_node": self.target_node,
				"num_target_node_pairs": len(self.target_node_pairs),
				"duration": duration,
				"honest_payments_per_second": honest_payments_per_second,
				"target_channel_capacity": target_channel_capacity,
				"results_normalized": normalize_results_for_duration,
				"num_runs_per_simulation": num_runs_per_simulation,
				"set_default_success_fee": self.set_default_success_fee,
				"default_success_base_fee": self.default_success_base_fee,
				"default_success_fee_rate": self.default_success_fee_rate,
				"no_balance_failures": self.no_balance_failures,
				"default_num_slots_per_channel_in_direction": self.default_num_slots_per_channel_in_direction,
				"max_num_attempts_per_route_honest": max_num_attempts_per_route_honest,
				"max_num_attempts_per_route_jamming": max_num_attempts_per_route_jamming,
				"dust_limit": ProtocolParams["DUST_LIMIT"],
				"min_processing_delay": PaymentFlowParams["MIN_DELAY"],
				"expected_extra_processing_delay": PaymentFlowParams["EXPECTED_EXTRA_DELAY"],
				"jam_delay": PaymentFlowParams["JAM_DELAY"]
			},
			"breakeven_stats": breakeven_stats,
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
		return breakeven_stats["breakeven_coeffs"]["base"], breakeven_stats["breakeven_coeffs"]["rate"]

	@staticmethod
	def get_breakeven_stats(results_honest, results_jamming, target_nodes):
		# Get simulation statistics about the breakeven coefficient in JSON format.
		breakeven_stats = {"breakeven_coeffs": {"base": None, "rate": None}, "stats": {}}
		breakeven_first_reached = False
		breakeven_upfront_base_coeff, breakeven_upfront_rate_coeff = None, None
		for result_honest in results_honest:
			upfront_base_coeff = result_honest["upfront_base_coeff"]
			upfront_rate_coeff = result_honest["upfront_rate_coeff"]
			# we assume that honest and jamming results are obtained from the same upfront coeff ranges
			result_jamming = [res for res in results_jamming if (
				res["upfront_base_coeff"] == upfront_base_coeff
				and res["upfront_rate_coeff"] == upfront_rate_coeff
			)][0]
			revenue_honest = sum(result_honest["revenues"][node] for node in target_nodes)
			revenue_jamming = sum(result_jamming["revenues"][node] for node in target_nodes)
			if revenue_honest == 0:
				logger.warning(f"Can't calculate jamming to honest ratio: honest revenue is zero!")
				jamming_to_honest_revenue_ratio = None
			else:
				jamming_to_honest_revenue_ratio = revenue_jamming / revenue_honest
			is_breakeven = jamming_to_honest_revenue_ratio > 1 if jamming_to_honest_revenue_ratio is not None else None
			if not breakeven_first_reached and is_breakeven:
				breakeven_upfront_base_coeff = upfront_base_coeff
				breakeven_upfront_rate_coeff = upfront_rate_coeff
				breakeven_first_reached = True
			if upfront_base_coeff not in breakeven_stats["stats"]:
				breakeven_stats["stats"][upfront_base_coeff] = {}
			if upfront_rate_coeff not in breakeven_stats["stats"][upfront_base_coeff]:
				breakeven_stats["stats"][upfront_base_coeff][upfront_rate_coeff] = {}
			breakeven_stats["stats"][upfront_base_coeff][upfront_rate_coeff]["is_breakeven"] = is_breakeven
			breakeven_stats["stats"][upfront_base_coeff][upfront_rate_coeff]["jamming_to_honest_revenue_ratio"] = jamming_to_honest_revenue_ratio
		breakeven_stats["breakeven_coeffs"]["base"] = breakeven_upfront_base_coeff
		breakeven_stats["breakeven_coeffs"]["rate"] = breakeven_upfront_rate_coeff
		return breakeven_stats

	@staticmethod
	def get_compact_output(results, relevant_nodes):
		# Get results for relevant nodes only.
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
		# Dump the results into a JSON file.
		with open("results/" + str(timestamp) + "-results" + ".json", "w", newline="") as f:
			json.dump(self.results, f, indent=4)

	def results_to_csv_file(self, timestamp):
		# Dump the results into a CSV file.
		# get all nodes names from some simulation result to avoid passing ln_graph here as a parameter
		nodes = sorted([node for node in next(iter(self.results["simulations"]["honest"]))["revenues"]])
		with open("results/" + str(timestamp) + "-results" + ".csv", "w", newline="") as f:
			writer = csv.writer(f, delimiter=",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
			for param_name in self.results["params"]:
				writer.writerow([param_name, self.results["params"][param_name]])
			writer.writerow("")
			writer.writerow(["first_breakeven_upfront_base_coef", self.results["breakeven_stats"]["breakeven_coeffs"]["base"]])
			writer.writerow(["first_breakeven_upfront_rate_coef", self.results["breakeven_stats"]["breakeven_coeffs"]["rate"]])
			writer.writerow("")
			writer.writerow([
				"upfront_base_coeff",
				"upfront_rate_coeff",
				"is_breakeven",
				"jamming_to_honest_revenue_ratio"])
			for base in self.results["breakeven_stats"]["stats"]:
				for rate in self.results["breakeven_stats"]["stats"][base]:
					writer.writerow([
						base,
						rate,
						self.results["breakeven_stats"]["stats"][base][rate]["is_breakeven"],
						self.results["breakeven_stats"]["stats"][base][rate]["jamming_to_honest_revenue_ratio"],
					])
			writer.writerow("")
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

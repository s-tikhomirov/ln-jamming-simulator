from simulator import Simulator
from schedule import Schedule, Event
from lnmodel import LNModel, RevenueType

from params import (
	honest_amount_function,
	honest_proccesing_delay_function,
	honest_generation_delay_function)
from params import ProtocolParams, PaymentFlowParams

import json
import csv
from statistics import mean


class Experiment:
	'''
		One experiment runs simulations with a parameter set,
		aggregates the results, and writes results to JSON and CSV files.
	'''

	def __init__(
		self,
		snapshot_json,
		simulation_duration,
		num_runs_per_simulation,
		success_base_fee,
		success_fee_rate,
		no_balance_failures,
		keep_receiver_upfront_fee,
		default_num_slots,
		max_num_attempts_per_route_honest,
		max_num_attempts_per_route_jamming):
		'''
			- snapshot_json
				A JSON object representing the LN graph. (Not a snapshot file.)

			- simulation_duration
				The simulation duration in seconds.

			- num_runs_per_simulation
				The number of simulations per parameter combination.

			- success_base_fee
				The success base fee.

			- success_fee_rate
				The success fee rate.

			- no_balance_failures
				If True, channels don't fail because of low balance.
				If False, channels fails. Probability depends on amount and capacity.

			- keep_receiver_upfront_fee
				If True, calculate all nodes' revenues in the same way.
				If False, manually set the receiver's upfront fee to zero.
				The rationale is that the sender had already subtracted the upfront fee
				from the amount when constructing the payment.

			- default_num_slots
				The number of slots each channel direction has unless set otherwise.

			- max_num_attempts_per_route_honest
				The maximal number of attempts an honest sender makes
				until the payment succeeds.
				Note: the attempts are made along the same route.

			- max_num_attempts_per_route_jamming
				The maximal number of attempts an jammer makes
				until the target channel runs out of slots.
				Note: the attempts are made along the same route.
		'''
		self.simulation_duration = simulation_duration
		self.num_runs_per_simulation = num_runs_per_simulation
		self.success_base_fee = success_base_fee
		self.success_fee_rate = success_fee_rate
		self.no_balance_failures = no_balance_failures
		self.keep_receiver_upfront_fee = keep_receiver_upfront_fee
		self.default_num_slots = default_num_slots
		self.max_num_attempts_per_route_honest = max_num_attempts_per_route_honest
		self.max_num_attempts_per_route_jamming = max_num_attempts_per_route_jamming
		self.ln_model = LNModel(snapshot_json, self.default_num_slots)
		self.ln_model.set_fee_function_for_all(
			RevenueType.SUCCESS,
			self.success_base_fee,
			self.success_fee_rate)
		self.simulator = Simulator(self.ln_model)
		self.dust_limit = ProtocolParams["DUST_LIMIT"]
		self.honest_payment_every_seconds = PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"]
		self.min_processing_delay = PaymentFlowParams["MIN_DELAY"]
		self.expected_extra_processing_delay = PaymentFlowParams["EXPECTED_EXTRA_DELAY"]
		self.jam_delay = self.min_processing_delay + 2 * self.expected_extra_processing_delay

	def set_sender(self, sender):
		self.sender = sender

	def set_receiver(self, receiver):
		self.receiver = receiver

	def set_target_node_pair(self, target_node_1, target_node_2):
		# The jammer sends all jams through the ch_dir
		# from target_node_1 to target_node_2.
		# ensure that there is a (directed) edge from target_node_1 to target_node_2
		assert(target_node_1 in self.ln_model.routing_graph.predecessors(target_node_2))
		self.target_node_pair = (target_node_1, target_node_2)

	def run_simulation(self, is_jamming):
		'''
			Run a simulation.
			A simulation includes multiple runs as specified in num_runs_per_simulation.
			The results are averaged.
		'''
		print("  Starting", "jamming" if is_jamming else "honest")
		tmp_num_sent, tmp_num_failed, tmp_num_reached_receiver = [], [], []
		tmp_revenues = {node: [] for node in self.ln_model.channel_graph.nodes}
		if is_jamming:
			# give attacker's channels twice as many slots as the default number of slots
			for special_node in (self.sender, self.receiver):
				for neighbor in self.ln_model.channel_graph.neighbors(special_node):
					self.ln_model.set_num_slots(special_node, neighbor, 2 * self.default_num_slots)
		for i in range(self.num_runs_per_simulation):
			print("    Simulation", i + 1, "of", self.num_runs_per_simulation)
			schedule = Schedule()
			if is_jamming:
				# initiate a jamming schedule with the initial jam event
				# (jam events will be pushed into the queue during processing)
				first_jam = Event(
					self.sender,
					self.receiver,
					amount=self.dust_limit,
					processing_delay=self.jam_delay,
					desired_result=False)
				schedule.put_event(0, first_jam)
				# execute the jamming schedule
				num_sent, num_failed, num_reached_receiver = self.simulator.execute_schedule(
					schedule,
					target_node_pair=self.target_node_pair,
					jam_with_insertion=True,
					no_balance_failures=self.no_balance_failures,
					keep_receiver_upfront_fee=self.keep_receiver_upfront_fee,
					simulation_cutoff=self.simulation_duration,
					max_num_attempts_per_route_jamming=self.max_num_attempts_per_route_jamming)
			else:
				# generate an honest schedule
				schedule.generate_schedule(
					senders_list=[self.sender],
					receivers_list=[self.receiver],
					amount_function=honest_amount_function,
					desired_result=True,
					payment_processing_delay_function=honest_proccesing_delay_function,
					payment_generation_delay_function=honest_generation_delay_function,
					scheduled_duration=self.simulation_duration)
				# execute the honest schedule
				num_sent, num_failed, num_reached_receiver = self.simulator.execute_schedule(
					schedule,
					no_balance_failures=self.no_balance_failures,
					keep_receiver_upfront_fee=self.keep_receiver_upfront_fee,
					simulation_cutoff=self.simulation_duration,
					max_num_attempts_per_route_honest=self.max_num_attempts_per_route_honest)
			tmp_num_sent.append(num_sent)
			tmp_num_failed.append(num_failed)
			tmp_num_reached_receiver.append(num_reached_receiver)
			for node in self.ln_model.channel_graph.nodes:
				upfront_revenue = self.ln_model.get_revenue(node, RevenueType.UPFRONT)
				success_revenue = self.ln_model.get_revenue(node, RevenueType.SUCCESS)
				tmp_revenues[node].append(upfront_revenue + success_revenue)
			self.ln_model.reset(self.default_num_slots)
		stats = {
			"num_sent": mean(tmp_num_sent),
			"num_failed": mean(tmp_num_failed),
			"num_reached_receiver": mean(tmp_num_reached_receiver)
		}
		revenues = {}
		for node in self.ln_model.channel_graph.nodes:
			revenues[node] = mean(tmp_revenues[node])
		return stats, revenues

	def run_simulation_pair(self, upfront_base_coeff, upfront_rate_coeff):
		'''
			Run a pair of simulations: honest case and jamming case, all else held equal,
			for a given pair of upfront fee coefficients.

			- upfront_base_coeff
				Upfront base fee is this many times the success base fee.

			- upfront_rate_coeff
				Upfront fee rate is this many times the success fee rate.
		'''
		print("\nStarting simulation pair:", upfront_base_coeff, upfront_rate_coeff)
		upfront_fee_base = self.success_base_fee * upfront_base_coeff
		upfront_fee_rate = self.success_fee_rate * upfront_rate_coeff
		self.ln_model.set_fee_function_for_all(RevenueType.UPFRONT, upfront_fee_base, upfront_fee_rate)
		stats, revenues = {}, {}
		stats["honest"], revenues["honest"] = self.run_simulation(is_jamming=False)
		stats["jamming"], revenues["jamming"] = self.run_simulation(is_jamming=True)
		return stats, revenues

	def run_simulations(self, upfront_base_coeff_range, upfront_rate_coeff_range):
		simulation_series_results = []
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				stats, revenues = self.run_simulation_pair(upfront_base_coeff, upfront_rate_coeff)
				result = {
					"upfront_base_coeff": upfront_base_coeff,
					"upfront_rate_coeff": upfront_rate_coeff,
					"stats": stats,
					"revenues": revenues
				}
				simulation_series_results.append(result)
		results = {
			"params": {
				"simulation_duration": self.simulation_duration,
				"num_runs_per_simulation": self.num_runs_per_simulation,
				"success_base_fee": self.success_base_fee,
				"success_fee_rate": self.success_fee_rate,
				"no_balance_failures": self.no_balance_failures,
				"keep_receiver_upfront_fee": self.keep_receiver_upfront_fee,
				"default_num_slots": self.default_num_slots,
				"max_num_attempts_per_route_honest": self.max_num_attempts_per_route_honest,
				"max_num_attempts_per_route_jamming": self.max_num_attempts_per_route_jamming,
				"dust_limit": self.dust_limit,
				"honest_payment_every_seconds": self.honest_payment_every_seconds,
				"min_processing_delay": self.min_processing_delay,
				"expected_extra_processing_delay": self.expected_extra_processing_delay,
				"jam_delay": self.jam_delay
			},
			"simulations": sorted(
				simulation_series_results,
				key=lambda d: (d["upfront_base_coeff"], d["upfront_rate_coeff"]),
				reverse=False)
		}
		self.results = results

	def results_to_json_file(self, timestamp):
		'''
			Dump the results into a JSON file.
		'''
		with open("results/" + str(timestamp) + "-results" + ".json", "w", newline="") as f:
			json.dump(self.results, f, indent=4)

	def results_to_csv_file(self, timestamp):
		'''
			Dump the results into a CSV file.
			First, write the simulation results.
			Then, write the experiment parameters (for reference).
			Format:
			upfront_base_coeff, upfront_rate_coeff, <honest stats>, <jamming stats>, <revenues>
			<empty line>
			parameter_name, parameter_value
			parameter_name, parameter_value
			etc
		'''
		nodes = sorted([node for node in self.ln_model.channel_graph.nodes])
		simulation_types = ["honest", "jamming"]
		revenue_titles = []
		for node in nodes:
			for simulation_type in simulation_types:
				revenue_titles.append(node[:1] + "_" + simulation_type[:1] + "_" + "revenue")
		with open("results/" + str(timestamp) + "-results" + ".csv", "w", newline="") as f:
			writer = csv.writer(f, delimiter=",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
			writer.writerow([
				"upfront_base_coeff",
				"upfront_rate_coeff",
				"h_sent",
				"h_failed",
				"h_reached_receiver",
				"j_sent",
				"j_failed",
				"j_reached_receiver"]
				+ revenue_titles)
			for result in self.results["simulations"]:
				revenues = [result["revenues"][simulation_type][node] for node in nodes for simulation_type in simulation_types]
				writer.writerow([
					result["upfront_base_coeff"],
					result["upfront_rate_coeff"],
					result["stats"]["honest"]["num_sent"],
					result["stats"]["honest"]["num_failed"],
					result["stats"]["honest"]["num_reached_receiver"],
					result["stats"]["jamming"]["num_sent"],
					result["stats"]["jamming"]["num_failed"],
					result["stats"]["jamming"]["num_reached_receiver"]]
					+ revenues)
			writer.writerow("")
			for param_name in self.results["params"]:
				writer.writerow([param_name, self.results["params"][param_name]])

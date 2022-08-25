from channel import FeeType

from statistics import mean

import logging
logger = logging.getLogger(__name__)


class Experiment:
	'''
		One experiment runs simulations with a parameter set,
		aggregates the results, and writes results to JSON and CSV files.
	'''

	def __init__(
		self,
		ln_model,
		simulator,
		num_runs_per_simulation):
		'''
			- ln_model
				An LNModel instance to run the experiment against.

			- simulator
				A Simulator instance with appropriate parameters set.

			- num_runs_per_simulation
				The number of simulations per parameter combination.
		'''
		self.ln_model = ln_model
		self.simulator = simulator
		self.num_runs_per_simulation = num_runs_per_simulation

	def run_simulations(self, schedule_generation_funciton, upfront_base_coeff_range, upfront_rate_coeff_range):
		def run_simulation():
			'''
				Run a simulation.
				A simulation includes multiple runs as specified in num_runs_per_simulation.
				The results are averaged.
			'''
			tmp_num_sent, tmp_num_failed, tmp_num_reached_receiver = [], [], []
			tmp_revenues = {node: [] for node in self.ln_model.channel_graph.nodes}
			for i in range(self.num_runs_per_simulation):
				logger.debug(f"Simulation {i + 1} of {self.num_runs_per_simulation}")
				# we can't generate schedules out of cycle because they get depleted during execution
				# (PriorityQueue does not support copying.)
				schedule = schedule_generation_funciton()
				num_sent, num_failed, num_reached_receiver = self.simulator.execute_schedule(
					schedule,
					self.ln_model)
				logger.debug(f"{num_sent} sent, {num_failed} failed, {num_reached_receiver} reached receiver")
				tmp_num_sent.append(num_sent)
				tmp_num_failed.append(num_failed)
				tmp_num_reached_receiver.append(num_reached_receiver)
				for node in self.ln_model.channel_graph.nodes:
					upfront_revenue = self.ln_model.get_revenue(node, FeeType.UPFRONT)
					success_revenue = self.ln_model.get_revenue(node, FeeType.SUCCESS)
					tmp_revenues[node].append(upfront_revenue + success_revenue)
				self.ln_model.reset()
			stats = {
				"num_sent": mean(tmp_num_sent),
				"num_failed": mean(tmp_num_failed),
				"num_reached_receiver": mean(tmp_num_reached_receiver)
			}
			revenues = {}
			for node in self.ln_model.channel_graph.nodes:
				revenues[node] = mean(tmp_revenues[node])
			return stats, revenues
		simulation_series_results = []
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				logger.info(f"Starting simulation with upfront fee coefficients: base {upfront_base_coeff}, rate {upfront_rate_coeff}")
				self.ln_model.set_upfront_fee_from_coeff_for_all(upfront_base_coeff, upfront_rate_coeff)
				stats, revenues = run_simulation()
				result = {
					"upfront_base_coeff": upfront_base_coeff,
					"upfront_rate_coeff": upfront_rate_coeff,
					"stats": stats,
					"revenues": revenues
				}
				simulation_series_results.append(result)
		return simulation_series_results

	def run_pair_of_simulations(
		self,
		schedule_generation_funciton_honest,
		schedule_generation_funciton_jamming,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		attackers_nodes,
		attackers_slots_coeff=2):
		'''
			Run two simulations that only differ in schedule generation functions (honest and jamming)
		'''

		# give attacker's channels twice as many slots as the default number of slots
		for attackers_node in attackers_nodes:
			for neighbor in self.ln_model.channel_graph.neighbors(attackers_node):
				self.ln_model.set_num_slots(
					attackers_node,
					neighbor,
					attackers_slots_coeff * self.ln_model.default_num_slots)

		logger.info("Starting jamming simulations")
		simulation_series_results_jamming = self.run_simulations(
			schedule_generation_funciton_jamming,
			upfront_base_coeff_range,
			upfront_rate_coeff_range)

		logger.info("Starting honest simulations")
		simulation_series_results_honest = self.run_simulations(
			schedule_generation_funciton_honest,
			upfront_base_coeff_range,
			upfront_rate_coeff_range)

		return simulation_series_results_honest, simulation_series_results_jamming

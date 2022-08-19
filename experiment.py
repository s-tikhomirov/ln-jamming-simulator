from lnmodel import RevenueType


from statistics import mean


class Experiment:
	'''
		One experiment runs simulations with a parameter set,
		aggregates the results, and writes results to JSON and CSV files.
	'''

	def __init__(
		self,
		ln_model,
		simulator,
		num_runs_per_simulation,
		success_base_fee,
		success_fee_rate):
		'''
			- ln_model
				An LNModel instance to run the experiment against.

			- simulator
				A Simulator instance with appropriate parameters set.

			- num_runs_per_simulation
				The number of simulations per parameter combination.

			- success_base_fee
				The success base fee.

			- success_fee_rate
				The success fee rate.
		'''
		self.ln_model = ln_model
		self.simulator = simulator
		self.num_runs_per_simulation = num_runs_per_simulation
		# Note: strictly speaking, fees are properties of ln_model, not an experiment.
		# We have to pass them here to calculate upfront fees from success-case fees
		# (we can't extract the success-case base and rate from functions stored in LNModel).
		# TODO: replace fee functions in LNModel with (base, rate) pairs.
		self.success_base_fee = success_base_fee
		self.success_fee_rate = success_fee_rate

	def set_target_node_pair(self, target_node_1, target_node_2):
		# The jammer sends all jams through the ch_dir
		# from target_node_1 to target_node_2.
		# ensure that there is a (directed) edge from target_node_1 to target_node_2
		assert(target_node_1 in self.ln_model.routing_graph.predecessors(target_node_2))
		self.target_node_pair = (target_node_1, target_node_2)

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
				#print("    Simulation", i + 1, "of", self.num_runs_per_simulation)
				# we can't generate schedules out of cycle because they get depleted during execution
				# (PriorityQueue does not support copying.)
				schedule = schedule_generation_funciton()
				num_sent, num_failed, num_reached_receiver = self.simulator.execute_schedule(
					schedule,
					self.ln_model)
				#print(num_sent, num_failed, num_reached_receiver)
				tmp_num_sent.append(num_sent)
				tmp_num_failed.append(num_failed)
				tmp_num_reached_receiver.append(num_reached_receiver)
				for node in self.ln_model.channel_graph.nodes:
					upfront_revenue = self.ln_model.get_revenue(node, RevenueType.UPFRONT)
					success_revenue = self.ln_model.get_revenue(node, RevenueType.SUCCESS)
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
				print("Starting simulation:", upfront_base_coeff, upfront_rate_coeff)
				upfront_fee_base = self.success_base_fee * upfront_base_coeff
				upfront_fee_rate = self.success_fee_rate * upfront_rate_coeff
				self.ln_model.set_fee_function_for_all(RevenueType.UPFRONT, upfront_fee_base, upfront_fee_rate)
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
		target_node_pair,
		attackers_slots_coeff=2):
		'''
			Run two simulations that only differ in schedule generation functions (honest and jamming)
		'''
		simulation_series_results_honest = self.run_simulations(
			schedule_generation_funciton_honest,
			upfront_base_coeff_range,
			upfront_rate_coeff_range)
		#print("Honest simulation complete")
		# give attacker's channels twice as many slots as the default number of slots
		# TODO: in graph simulations, exclude attacker's channels from honest payment flow
		for attackers_node in attackers_nodes:
			for neighbor in self.ln_model.channel_graph.neighbors(attackers_node):
				self.ln_model.set_num_slots(
					attackers_node,
					neighbor,
					attackers_slots_coeff * self.ln_model.default_num_slots)
		self.simulator.target_node_pair = target_node_pair
		simulation_series_results_jamming = self.run_simulations(
			schedule_generation_funciton_jamming,
			upfront_base_coeff_range,
			upfront_rate_coeff_range)
		#print("Jamming simulation complete")
		return simulation_series_results_honest, simulation_series_results_jamming

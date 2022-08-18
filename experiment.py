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

		'''
		# Common properties for any type of simulation
		self.num_runs_per_simulation = num_runs_per_simulation

		# Properties of the graph
		self.success_base_fee = success_base_fee
		self.success_fee_rate = success_fee_rate
		self.ln_model = ln_model
		self.simulator = simulator

		# used in Schedule construction only?
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

	def run_simulations(self, ln_model, schedule_generation_funciton, upfront_base_coeff_range, upfront_rate_coeff_range):
		def run_simulation():
			'''
				Run a simulation.
				A simulation includes multiple runs as specified in num_runs_per_simulation.
				The results are averaged.
			'''
			tmp_num_sent, tmp_num_failed, tmp_num_reached_receiver = [], [], []
			tmp_revenues = {node: [] for node in ln_model.channel_graph.nodes}
			for i in range(self.num_runs_per_simulation):
				#print("    Simulation", i + 1, "of", self.num_runs_per_simulation)
				# we can't generate schedules out of cycle because they get depleted during execution
				# (PriorityQueue does not support copying.)
				schedule = schedule_generation_funciton()
				num_sent, num_failed, num_reached_receiver = self.simulator.execute_schedule(
					schedule,
					ln_model)
				tmp_num_sent.append(num_sent)
				tmp_num_failed.append(num_failed)
				tmp_num_reached_receiver.append(num_reached_receiver)
				for node in ln_model.channel_graph.nodes:
					upfront_revenue = ln_model.get_revenue(node, RevenueType.UPFRONT)
					success_revenue = ln_model.get_revenue(node, RevenueType.SUCCESS)
					tmp_revenues[node].append(upfront_revenue + success_revenue)
				ln_model.reset()
			stats = {
				"num_sent": mean(tmp_num_sent),
				"num_failed": mean(tmp_num_failed),
				"num_reached_receiver": mean(tmp_num_reached_receiver)
			}
			revenues = {}
			for node in ln_model.channel_graph.nodes:
				revenues[node] = mean(tmp_revenues[node])
			return stats, revenues
		simulation_series_results = []
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				print("\nStarting simulation:", upfront_base_coeff, upfront_rate_coeff)
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

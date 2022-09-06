from chdir import FeeType, ErrorType, ChannelDirection
from channel import Channel
from params import ProtocolParams
from payment import Payment
from router import Router

from statistics import mean
import networkx as nx

import logging
logger = logging.getLogger(__name__)


class Simulator:
	'''
		The Simulator class executes a Schedule of Events.
		For each Event, it builds a route, creates a Payment, and routes it.
		The resulting changes in revenues are written into the LNModel.
	'''

	def __init__(
		self,
		ln_model,
		target_hops,
		max_num_attempts_per_route_honest,
		max_num_attempts_per_route_jamming,
		max_num_routes_honest,
		max_num_routes_jamming=None,
		num_runs_per_simulation=1,
		subtract_last_hop_upfront_fee_for_honest_payments=True,
		jammer_must_route_via_nodes=[],
		max_target_hops_per_route=10):
		'''
			- ln_model
				An instance of LNModel to run the simulations with.

			- target_hops
				What the attacker wants to jam.

			- max_num_attempts_per_route_honest
				The maximum number of attempts to send an honest payment.

			- max_num_attempts_per_route_jamming
				The maximul number of attempts to send a jam (which is probably higher than that for honest payments).

			- max_num_routes_honest
				The maximal number of different routes to try before an honest payment reaches the receiver.

			- max_num_routes_jamming
				The maximal number of different routes to try before all target hops are fully jammed.

			- num_runs_per_simulation
				The number of runs per simulation to average the results across.

			- subtract_last_hop_upfront_fee_for_honest_payments
				Apply body_for_amount at Payment construction for honest payment.
				Jams are always constructed without such adjustment to stay above the dust limit at all hops.

			- jammer_must_route_via_nodes
				Override the router logic in favor of a hard-coded route.

			- max_target_hops_per_route
				Max desired number of target hops in a jammer's route.
		'''
		self.ln_model = ln_model
		self.target_hops = target_hops
		self.max_num_attempts_per_route_honest = max_num_attempts_per_route_honest
		self.max_num_attempts_per_route_jamming = max_num_attempts_per_route_jamming
		self.max_num_routes_honest = max_num_routes_honest
		# we may not finish jamming a hop due to roll-back of the last looped jam
		# we can have at most as many unjammed slots as hops in the whole route
		# we jam is separately if needed with no-repeated-hops-allowed route
		max_default_routes_per_target_hop = 1 + ProtocolParams["MAX_ROUTE_LENGTH"]
		self.max_num_routes_jamming = len(self.target_hops) * max_default_routes_per_target_hop if max_num_routes_jamming is None else max_num_routes_jamming
		self.subtract_last_hop_upfront_fee_for_honest_payments = subtract_last_hop_upfront_fee_for_honest_payments
		self.num_runs_per_simulation = num_runs_per_simulation
		self.jammer_must_route_via_nodes = jammer_must_route_via_nodes
		self.max_target_hops_per_route = max_target_hops_per_route

	def run_simulation_series(self, schedule_generation_funciton, upfront_base_coeff_range, upfront_rate_coeff_range):
		simulation_series_results = []
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				logger.info(f"Starting simulation with upfront fee coefficients: base {upfront_base_coeff}, rate {upfront_rate_coeff}")
				self.ln_model.set_upfront_fee_from_coeff_for_all(upfront_base_coeff, upfront_rate_coeff)
				stats, revenues = self.run_simulation(schedule_generation_funciton)
				result = {
					"upfront_base_coeff": upfront_base_coeff,
					"upfront_rate_coeff": upfront_rate_coeff,
					"stats": stats,
					"revenues": revenues
				}
				simulation_series_results.append(result)
		return simulation_series_results

	def run_simulation(self, schedule_generation_funciton):
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
			num_sent, num_failed, num_reached_receiver = self.execute_schedule(schedule)
			logger.debug(f"{num_sent} sent, {num_failed} failed, {num_reached_receiver} reached receiver")
			tmp_num_sent.append(num_sent)
			tmp_num_failed.append(num_failed)
			tmp_num_reached_receiver.append(num_reached_receiver)
			for node in self.ln_model.channel_graph.nodes:
				upfront_revenue = self.ln_model.get_revenue(node, FeeType.UPFRONT)
				success_revenue = self.ln_model.get_revenue(node, FeeType.SUCCESS)
				tmp_revenues[node].append(upfront_revenue + success_revenue)
		stats = {
			"num_sent": mean(tmp_num_sent),
			"num_failed": mean(tmp_num_failed),
			"num_reached_receiver": mean(tmp_num_reached_receiver)
		}
		revenues = {}
		for node in self.ln_model.channel_graph.nodes:
			revenues[node] = mean(tmp_revenues[node])
		return stats, revenues

	def execute_schedule(self, schedule):
		self.ln_model.reset()
		self.now = -1
		self.schedule = schedule
		self.num_sent_total, self.num_failed_total, self.num_reached_receiver_total = 0, 0, 0
		while not self.schedule.is_empty():
			new_time, event = self.schedule.get_event()
			if new_time > self.now:
				logger.debug(f"Current time: {new_time}")
				pass
			if new_time > self.schedule.end_time:
				break
			self.now = new_time
			logger.debug(f"Got event: {event}")
			is_jam = event.desired_result is False
			if is_jam:
				if self.jammer_must_route_via_nodes:
					self.handle_jam_with_static_route(event)
				else:
					self.handle_jam_with_router(event)
				next_batch_time = self.now + event.processing_delay
				logger.debug(f"Moving to the next batch: putting jam {event} into schedule for time {next_batch_time}")
				self.schedule.put_event(next_batch_time, event)
			else:
				self.handle_honest_payment(event)
		if self.schedule.is_empty():
			logger.info(f"Depleted the schedule with end time {self.schedule.end_time}, last event was at {self.now}")
		else:
			logger.info(f"Reached schedule end time {self.schedule.end_time}, last event was at {self.now}")
		self.now = self.schedule.end_time
		logger.debug(f"Finalizing in-flight HTLCs...")
		self.ln_model.finalize_in_flight_htlcs(self.now)
		logger.info(f"Schedule executed: {self.num_sent_total} sent, {self.num_failed_total} failed, {self.num_reached_receiver_total} reached receiver")
		return self.num_sent_total, self.num_failed_total, self.num_reached_receiver_total

	def handle_jam_with_static_route(self, event):
		rg = self.ln_model.routing_graph
		must_nodes = self.jammer_must_route_via_nodes
		assert(rg.has_edge("JammerSender", must_nodes[0]))
		assert(all(rg.has_edge(hop[0], hop[1]) for hop in zip(must_nodes, must_nodes[1:])))
		assert(rg.has_edge(must_nodes[-1], "JammerReceiver"))
		route_from_sender = nx.shortest_path(rg, "JammerSender", must_nodes[0])
		route_to_receiver = nx.shortest_path(rg, must_nodes[-1], "JammerReceiver")
		route = route_from_sender + must_nodes[1:-1] + route_to_receiver
		num_sent, num_failed, num_reached_receiver, jammed_hop = self.send_jam_via_route(event, route)
		self.num_sent_total += num_sent
		self.num_failed_total += num_failed
		self.num_reached_receiver_total += num_reached_receiver
		logger.debug(f"Jammed hop {jammed_hop}")

	def handle_jam_with_router(self, event):
		max_num_routes = self.max_num_routes_jamming
		target_hops_unjammed = self.target_hops.copy()
		router = Router(self.ln_model, event.amount, event.sender, event.receiver)
		router.update_route_generator(target_hops_unjammed)  # , max_route_length=8)
		for num_route in range(max_num_routes):
			logger.debug(f"Trying route {num_route + 1} of max {max_num_routes} ({len(target_hops_unjammed)} / {len(self.target_hops)} hops definitely unjammed)")
			logger.debug(f"Definitely unjammed hops: {target_hops_unjammed}")
			if not target_hops_unjammed:
				logger.debug(f"No unjammed target hops left, no need to try further routes")
				break
			try:
				route = router.get_route()
				logger.debug(f"Found route of length {len(route)}: {route}")
			except StopIteration:
				logger.debug(f"No route from {event.sender} to {event.receiver} via any of {target_hops_unjammed}")
				break
			num_sent, num_failed, num_reached_receiver, jammed_hop = self.send_jam_via_route(event, route)
			self.num_sent_total += num_sent
			self.num_failed_total += num_failed
			self.num_reached_receiver_total += num_reached_receiver
			logger.debug(f"Jammed hop {jammed_hop}")
			# exclude jammed hop from the router # we can't route through the jammed hop it anyway, no matter if it's among target hops or not
			# the only exception is the jammer's own channels
			if "JammerSender" in jammed_hop or "JammerReceiver" in jammed_hop:
				logger.error(f"Jammer's node is in jammed hop {jammed_hop}")
				logger.info(f"{self.ln_model.get_hop(*jammed_hop).get_jammed_status(jammed_hop[0] < jammed_hop[1], self.now)}")
			assert("JammerSender" not in jammed_hop and "JammerReceiver" not in jammed_hop)
			assert(jammed_hop in target_hops_unjammed or jammed_hop not in self.target_hops)
			# only exclude the newly jammed hop from graph if it's REALLY jammed
			if self.ln_model.hop_is_jammed(jammed_hop, self.now):
				logger.debug(f"Removing {jammed_hop} from router")
				router.remove_hop(jammed_hop)
				if jammed_hop in target_hops_unjammed:
					logger.debug(f"Removing {jammed_hop} from unjammed hops {target_hops_unjammed}")
					target_hops_unjammed.remove(jammed_hop)
					router.update_route_generator(target_hops_unjammed)
			# check if need to transit to no-repeated-hops mode
			if router.allow_repeated_hops and not target_hops_unjammed:
				all_target_hops_are_really_jammed = all(self.ln_model.hop_is_jammed(hop, self.now) for hop in self.target_hops)
				if not all_target_hops_are_really_jammed:
					logger.debug(f"Some target hops may be still unjammed due to roll-back of looped jams!")
					logger.debug(f"Target hops REALLY jammed? {all_target_hops_are_really_jammed}")
					logger.debug(f"Target hops WE THINK are unjammed: {target_hops_unjammed}")
					target_hops_unjammed = [hop for hop in self.target_hops if not self.ln_model.hop_is_jammed(hop, self.now)]
					logger.info(f"Jamming the last unjammed hops {target_hops_unjammed} with no-repeated-hops routes")
					router.update_route_generator(target_hops_unjammed, allow_repeated_hops=False)
				else:
					logger.debug(f"All target hops jammed at time {self.now}")
		#logger.info(f"Out of loop; num_route = {num_route}")
		#logger.info(f"Target hops jammed status: {[(hop, self.ln_model.get_hop(*hop).get_jammed_status(hop[0] < hop[1], self.now)) for hop in self.target_hops]}")
		target_hops_left_unjammed = [hop for hop in self.target_hops if not self.ln_model.hop_is_jammed(hop, self.now)]
		if target_hops_left_unjammed:
			# Note: for hard-coded routes with a fixed number of slots, we actually jam the whole route at once
			# But we can't confirm this because we only get a NO_SLOTS error from the first hop in the route
			logger.warning(f"Couldn't jam hops {target_hops_left_unjammed} after {num_route+1} routes at time {self.now}.")

	def send_jam_via_route(self, event, route):
		assert(event.desired_result is False)
		logger.debug(f"Sending jam via {route}")
		logger.debug(f"Receiver will get {event.amount} in payment body")
		p = self.create_payment(route, event.amount, event.processing_delay, event.desired_result)
		num_sent, num_failed, num_reached_receiver = 0, 0, 0
		for attempt_num in range(self.max_num_attempts_per_route_jamming):
			reached_receiver, last_node_reached, first_node_not_reached, error_type = self.ln_model.attempt_send_payment(
				p,
				event.sender,
				self.now,
				attempt_id=str(attempt_num))
			assert(error_type is not None)
			num_sent += 1
			if error_type is not None:
				num_failed += 1
			if reached_receiver:
				logger.debug(f"Jam reached receiver {last_node_reached} at attempt {attempt_num}")
				num_reached_receiver += 1
			else:
				logger.debug(f"Jam failed at {last_node_reached}-{first_node_not_reached} with {error_type} at attempt {attempt_num}")
				if error_type in (ErrorType.LOW_BALANCE, ErrorType.FAILED_DELIBERATELY):
					logger.debug(f"Continue the batch at time {self.now}")
				elif error_type == ErrorType.NO_SLOTS:
					sender, pre_receiver = route[0], route[-2]
					if last_node_reached in (sender, pre_receiver):
						# FIXME: this check is incorrect for circular routes
						#logger.warning(f"Slots depleted at {last_node_reached}-{first_node_not_reached}. Allocate more slots to jammer's channels?")
						pass
					else:
						logger.debug(f"Route {route} jammed at time {self.now}")
					break
		if attempt_num == self.max_num_attempts_per_route_jamming and error_type != ErrorType.NO_SLOTS:
			logger.warning(f"Coundn't jam route {route} at time {self.now} after {attempt_num} attempts")
		return num_sent, num_failed, num_reached_receiver, (last_node_reached, first_node_not_reached)

	def handle_honest_payment(self, event):
		if event.must_route_via_nodes:
			route = [event.sender] + event.must_route_via_nodes + [event.receiver]
			num_sent, num_failed, num_reached_receiver = self.send_honest_payment_via_route(event, route)
			self.num_sent_total += num_sent
			self.num_failed_total += num_failed
			self.num_reached_receiver_total += num_reached_receiver
		else:
			routes = self.ln_model.get_shortest_routes(event.sender, event.receiver, event.amount)
			for num_route in range(self.max_num_routes_honest):
				try:
					route = next(routes)
					logger.debug(f"Found route: {route}")
				except StopIteration:
					logger.debug("No route, skipping event")
					break
				num_sent, num_failed, num_reached_receiver = self.send_honest_payment_via_route(event, route)
				self.num_sent_total += num_sent
				self.num_failed_total += num_failed
				self.num_reached_receiver_total += num_reached_receiver
				if num_reached_receiver > 0:
					logger.debug(f"Honest payment reached receiver at route {num_route + 1}, no need to try further routes")
					break

	def send_honest_payment_via_route(self, event, route):
		assert(event.desired_result is True)
		if not self.subtract_last_hop_upfront_fee_for_honest_payments:
			receiver_amount = event.amount
		else:
			logger.info(f"Subtracting last-hop upfront fee from amount {event.amount}")
			pre_receiver, receiver = route[-2], route[-1]
			logger.debug(f"Pre-receiver, receiver: {pre_receiver} {receiver} ")
			chosen_cid = self.ln_model.get_cheapest_cid_in_hop(pre_receiver, receiver, event.amount)
			chosen_ch_dir = self.ln_model.get_hop(receiver, pre_receiver).get_channel(chosen_cid).directions[pre_receiver < receiver]
			receiver_amount = Simulator.body_for_amount(event.amount, chosen_ch_dir.upfront_fee_function)
		logger.debug(f"Receiver will get {receiver_amount} in payment body")
		p = self.create_payment(route, receiver_amount, event.processing_delay, event.desired_result)
		num_sent, num_failed, num_reached_receiver = 0, 0, 0
		for attempt_num in range(self.max_num_attempts_per_route_honest):
			reached_receiver, last_node_reached, first_node_not_reached, error_type = self.ln_model.attempt_send_payment(
				p,
				event.sender,
				self.now,
				attempt_id=str(attempt_num))
			num_sent += 1
			if reached_receiver:
				logger.debug(f"Payment reached receiver after {attempt_num} attempts")
				num_reached_receiver += 1
				break
			elif error_type is not None:
				logger.debug(f"Payment failed at {last_node_reached}-{first_node_not_reached} with {error_type} at attempt {attempt_num}")
				num_failed += 1
		return num_sent, num_failed, num_reached_receiver

	def create_payment(self, route, amount, processing_delay, desired_result):
		p, u_nodes, d_nodes = None, route[:-1], route[1:]
		for u_node, d_node in reversed(list(zip(u_nodes, d_nodes))):
			#logger.debug(f"Wrapping payment for fee policy from {u_node} to {d_node}")
			chosen_cid = self.ln_model.get_cheapest_cid_in_hop(u_node, d_node, amount)
			chosen_ch_dir = self.ln_model.get_hop(u_node, d_node).get_channel(chosen_cid).directions[u_node < d_node]
			#logger.debug(f"Chosen channel {chosen_cid}")
			is_last_hop = p is None
			p = Payment(
				downstream_payment=p,
				downstream_node=d_node,
				upfront_fee_function=chosen_ch_dir.upfront_fee_function,
				success_fee_function=chosen_ch_dir.success_fee_function,
				desired_result=desired_result if is_last_hop else None,
				processing_delay=processing_delay if is_last_hop else None,
				receiver_amount=amount if is_last_hop else None)
		return p

	@staticmethod
	def body_for_amount(target_amount, upfront_fee_function, precision=1, max_steps=50):
		'''
			Given target_amount and fee function, find amount such that:
			amount + fee(amount) ~ target_amount
		'''
		assert(precision >= 1)
		min_body, max_body, num_step = 0, target_amount, 0
		while num_step < max_steps:
			body = round((min_body + max_body) / 2)
			fee = upfront_fee_function(body)
			amount = body + fee
			if abs(target_amount - amount) < precision:
				break
			if amount < target_amount:
				min_body = body
			else:
				max_body = body
			num_step += 1
		if abs(target_amount - amount) >= precision:
			logger.debug(f"Couldn't reach precision {precision} in body for amount {target_amount}!")
			logger.debug(f"Made {num_step} of {max_steps} allowed.")
			assert(num_step == max_steps)
		logger.debug(f"{num_step}")
		return body

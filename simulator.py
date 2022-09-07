from statistics import mean

from direction import Direction
from channelindirection import ErrorType, FeeType
from params import ProtocolParams
from payment import Payment
from router import Router

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
		max_target_hops_per_route=10,
		max_route_length=10):
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

			- max_route_length
				Max number of hops per route.
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
		self.max_route_length = max_route_length

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

	def reset(self):
		self.ln_model.reset_all_slots()
		self.ln_model.reset_all_revenues()
		self.now = -1
		self.num_sent_total, self.num_failed_total, self.num_reached_receiver_total = 0, 0, 0

	def execute_schedule(self, schedule):
		self.reset()
		self.schedule = schedule
		while not self.schedule.no_more_events():
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
				logger.info(f"Start handling jam batch at time {self.now}")
				if self.jammer_must_route_via_nodes:
					self.handle_jam_with_static_route(event)
				else:
					self.handle_jam_with_router(event)
				next_batch_time = self.now + event.processing_delay
				if next_batch_time > self.schedule.end_time:
					break
				logger.debug(f"Moving to the next jam batch")
				logger.debug(f"Pushing jam {event} into schedule for time {next_batch_time}")
				self.schedule.put_event(next_batch_time, event)
			else:
				self.handle_honest_payment(event)
		if self.schedule.no_more_events():
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
		#route_from_sender = nx.shortest_path(rg, "JammerSender", must_nodes[0])
		#route_to_receiver = nx.shortest_path(rg, must_nodes[-1], "JammerReceiver")
		# FIXME: ensure that routes fit for jams here?
		route = ["JammerSender"] + must_nodes + ["JammerReceiver"]
		num_sent, num_failed, num_reached_receiver, last_node_reached, first_node_not_reached = self.send_jam_via_route(event, route)
		assert(first_node_not_reached is not None)
		jammed_hop = (last_node_reached, first_node_not_reached)
		self.num_sent_total += num_sent
		self.num_failed_total += num_failed
		self.num_reached_receiver_total += num_reached_receiver
		logger.debug(f"Jammed hop {jammed_hop}")

	def all_target_hops_are_really_jammed(self):
		return all(self.ln_model.get_hop(*hop).cannot_forward(Direction(*hop), self.now) for hop in self.target_hops)

	def get_jammed_status_of_hops(self, hops):
		return [
			(
				Router.shorten_ids(hop),
				self.ln_model.get_hop(*hop).cannot_forward(Direction(*hop), self.now),
				self.ln_model.get_hop(*hop).get_total_num_slots_occupied_in_direction(Direction.Alph)
			) for hop in hops]

	def handle_jam_with_router(self, event):
		max_num_routes = self.max_num_routes_jamming
		target_hops_unjammed = self.target_hops.copy()
		router = Router(
			self.ln_model,
			event.amount,
			event.sender,
			event.receiver,
			self.max_target_hops_per_route,
			self.max_route_length)
		router.update_route_generator(target_hops_unjammed)
		for num_route in range(max_num_routes):
			logger.debug(f"Trying jamming route {num_route + 1} of max {max_num_routes}")
			logger.debug(f"At least {len(target_hops_unjammed)} / {len(self.target_hops)} target hops still unjammed")
			if not target_hops_unjammed:
				logger.debug(f"No unjammed target hops left, no need to try further routes")
				break
			try:
				route = router.get_route()
			except StopIteration:
				logger.warning(f"No route from {event.sender} to {event.receiver} via any of {target_hops_unjammed}")
				break
			#logger.debug(f"Found route of length {len(route)}")
			num_sent, num_failed, num_reached_receiver, last_node_reached, first_node_not_reached = self.send_jam_via_route(event, route)
			self.num_sent_total += num_sent
			self.num_failed_total += num_failed
			self.num_reached_receiver_total += num_reached_receiver
			if first_node_not_reached is not None:
				jammed_hop = (last_node_reached, first_node_not_reached)
				logger.debug(f"Jammed hop {jammed_hop}")
				if "JammerSender" in jammed_hop or "JammerReceiver" in jammed_hop:
					logger.warning(f"Jammer's node is in a jammed hop {jammed_hop}. Assign more slots to the jammer!")
				assert(jammed_hop in target_hops_unjammed or jammed_hop not in self.target_hops)
				# Only if the newly jammed hop occurs in the route exactly once, can we be sure it's really jammed!
				# Otherwise, if the hop became jammed on a non-first occurrence in the route,
				# some slots would be freed up when the jam rolls back.
				# In that case, we don't exclude the hop from the list of unjammed hop, and move on to the next route.
				# The hop will be eventually jammed via some future (presumably non-looped) route.
				if Router.num_hop_occurs_in_path(jammed_hop, route) == 1:
					logger.debug(f"Removing {jammed_hop} from router (occurs only once in path)")
					router.remove_hop(jammed_hop)
					if jammed_hop in target_hops_unjammed:
						logger.debug(f"Removing {jammed_hop} from unjammed hops {target_hops_unjammed}")
						target_hops_unjammed.remove(jammed_hop)
						router.update_route_generator(target_hops_unjammed)
				else:
					logger.debug(f"Hop {jammed_hop} may not be fully jammed!")
					logger.debug(f"Jammed hop {jammed_hop} occurs {Router.num_hop_occurs_in_path(jammed_hop, route)} times in route {route}")
			else:
				logger.debug(f"All jams reached receiver for route {route}")
				#logger.debug(f"Allow for more attempts per route (now at {self.max_num_attempts_per_route_jamming})!")
				target_hops_unjammed_in_this_route = [hop for hop in Router.get_hops(route) if (
					hop in self.target_hops
					and self.ln_model.get_hop(*hop).can_forward(Direction(*hop), self.now)
				)]
				logger.debug(f"Target hops unjammed in this route: {self.get_jammed_status_of_hops(target_hops_unjammed_in_this_route)}")
			logger.debug(f"All target hops jammed status: {self.get_jammed_status_of_hops(self.target_hops)}")
		if not self.all_target_hops_are_really_jammed():
			target_hops_left_unjammed = [hop for hop in self.target_hops if (
				self.ln_model.get_hop(*hop).can_forward(Direction(*hop), self.now)
			)]
			# sic! num_routes, not (num_routes + 1): though we start at zero, we count the last interation which breaks before producing a route
			logger.warning(f"Couldn't jam {len(target_hops_left_unjammed)} target hops after {num_route} routes at time {self.now}.")
			logger.warning(f"Unjammed target hops: {self.get_jammed_status_of_hops(target_hops_left_unjammed)}")
		else:
			logger.info(f"All target hops are jammed at time {self.now}")

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
			assert(reached_receiver == (first_node_not_reached is None))
			if reached_receiver:
				logger.debug(f"Jam reached receiver {last_node_reached} at attempt {attempt_num}")
				num_reached_receiver += 1
			else:
				logger.debug(f"Jam failed at {last_node_reached}-{first_node_not_reached} with {error_type} at attempt {attempt_num}")
				if error_type in (ErrorType.LOW_BALANCE, ErrorType.FAILED_DELIBERATELY):
					logger.debug(f"Continue the batch at time {self.now}")
				elif error_type == ErrorType.NO_SLOTS:
					logger.debug(f"Route {route} jammed at time {self.now}")
					break
		return num_sent, num_failed, num_reached_receiver, last_node_reached, first_node_not_reached

	def get_shortest_route_via_nodes(self, nodes, amount):
		route = [nodes[0]]
		logger.debug(f"Constructing route via {nodes} for {amount}")
		for (u_node, d_node) in Router.get_hops(nodes):
			logger.debug(f"Constructing sub-route {u_node}-{d_node}")
			sub_routes = self.ln_model.get_shortest_routes(u_node, d_node, amount)
			if sub_routes is None:
				logger.debug(f"No route from {u_node} to {d_node} for amount {amount}")
				return None
			else:
				try:
					sub_route = next(sub_routes)
					logger.debug(f"Sub-route is: {sub_route}")
				except StopIteration:
					logger.debug(f"Sub-route from {u_node} to {d_node} for amount {amount} is None")
					return None
				if sub_route is None:
					return None
				else:
					route.extend(sub_route[1:])
					logger.debug(f"Route now is: {route}")
		logger.debug(f"Final route is: {route}")
		return route

	def handle_honest_payment(self, event):
		if event.must_route_via_nodes:
			must_nodes = [event.sender] + event.must_route_via_nodes + [event.receiver]
			route = self.get_shortest_route_via_nodes(must_nodes, event.amount)
			if route is None:
				logger.debug(f"Couldn't handle honest payment {event}, moving on")
			else:
				logger.debug(f"Constructed route from {event.sender} to {event.receiver} via given nodes {event.must_route_via_nodes}: {route}")
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

	def adjust_body_for_route(self, route, amount):
		assert len(route) >= 2
		pre_receiver, receiver = route[-2], route[-1]
		logger.debug(f"Adjusting payment body for the last hop {pre_receiver}-{receiver}")
		chosen_ch = self.ln_model.get_hop(pre_receiver, receiver).get_cheapest_channel_maybe_can_forward(
			Direction(pre_receiver, receiver),
			amount)
		chosen_cid = chosen_ch.get_cid()
		logger.debug(f"Chosen cheapest channel for payment body adjustment: {chosen_cid}")
		chosen_ch_in_dir = chosen_ch.in_direction(Direction(pre_receiver, receiver))
		return Simulator.body_for_amount(amount, chosen_ch_in_dir.upfront_fee_function)

	def send_honest_payment_via_route(self, event, route):
		assert event.desired_result is True
		if self.subtract_last_hop_upfront_fee_for_honest_payments:
			last_hop_body = self.adjust_body_for_route(route, event.amount)
		else:
			last_hop_body = event.amount
		logger.debug(f"Receiver will get {last_hop_body} in payment body")
		p = self.create_payment(route, last_hop_body, event.processing_delay, event.desired_result)
		num_sent, num_failed, num_reached_receiver = 0, 0, 0
		for attempt_num in range(self.max_num_attempts_per_route_honest):
			reached_receiver, last_node_reached, first_node_not_reached, error_type = self.ln_model.attempt_send_payment(
				p,
				event.sender,
				self.now,
				attempt_id=str(attempt_num))
			num_sent += 1
			if reached_receiver:
				logger.debug(f"Payment reached the receiver after {attempt_num + 1} attempts")
				num_reached_receiver += 1
				break
			elif error_type is not None:
				logger.debug(f"Payment failed at {last_node_reached}-{first_node_not_reached} with {error_type} at attempt {attempt_num}")
				num_failed += 1
		return num_sent, num_failed, num_reached_receiver

	def create_payment(self, route, amount, processing_delay, desired_result):
		p, u_nodes, d_nodes = None, route[:-1], route[1:]
		for u_node, d_node in reversed(list(zip(u_nodes, d_nodes))):
			logger.debug(f"Wrapping payment for fee policy from {u_node} to {d_node}")
			# Note: we model the sender's payment construction here
			# The sender can't check if a hop really can forward (i.e., is not jammed)
			# TODO: implement proper logic like: if the cheapest channel is jammed, choose another one
			# also note: this check is time-independent: we can check capacity and enabled status without time
			# only jamming status check is time-sensitive, but this is unavailable for us here
			chosen_ch = self.ln_model.get_hop(u_node, d_node).get_cheapest_channel_maybe_can_forward(
				Direction(u_node, d_node),
				amount)
			chosen_cid = chosen_ch.get_cid()
			logger.debug(f"Suggested cheapest cid: {chosen_cid}")
			hop = self.ln_model.get_hop(u_node, d_node)
			#logger.debug(f"Hop of this cid: {hop}")
			channel = hop.get_channel(chosen_cid)
			#logger.debug(f"Channel of chosen cid {chosen_cid}: {channel}")
			chosen_ch_in_dir = channel.in_direction(Direction(u_node, d_node))
			is_last_hop = p is None
			p = Payment(
				downstream_payment=p,
				downstream_node=d_node,
				upfront_fee_function=chosen_ch_in_dir.upfront_fee_function,
				success_fee_function=chosen_ch_in_dir.success_fee_function,
				desired_result=desired_result if is_last_hop else None,
				processing_delay=processing_delay if is_last_hop else None,
				last_hop_body=amount if is_last_hop else None)
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
		return body

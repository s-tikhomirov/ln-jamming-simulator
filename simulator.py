from statistics import mean
from copy import deepcopy
from functools import partial
from collections import defaultdict

from direction import Direction
from channelindirection import ErrorType, FeeType, ChannelInDirection
from params import ProtocolParams, FeeParams
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
		max_num_routes,
		max_num_attempts_per_route,
		max_route_length,
		num_runs_per_simulation):
		'''
			- ln_model
				An instance of LNModel to run the simulations with.

			- target_node_pairs
				What the attacker wants to jam.

			- target_node
				Only used for accounting of how many times we hit it during jamming.

			- max_num_attempts_per_route_honest
				The maximum number of attempts to send an honest payment.

			- max_num_attempts_per_route_jamming
				The maximul number of attempts to send a jam (which is probably higher than that for honest payments).

			- max_num_routes_honest
				The maximal number of different routes to try before an honest payment reaches the receiver.

			- max_num_routes_jamming
				The maximal number of different routes to try before all target node pairs are fully jammed.

			- num_runs_per_simulation
				The number of runs per simulation to average the results across.

			- subtract_last_hop_upfront_fee_for_honest_payments
				Apply body_for_amount at Payment construction for honest payment.
				Jams are always constructed without such adjustment to stay above the dust limit at all hops.

			- jammer_must_route_via_nodes
				Override the router logic in favor of a hard-coded route.

			- max_target_node_pairs_per_route
				Max desired number of target node pairs in a jammer's route.

			- max_route_length
				Max number of hops per route.
		'''
		self.ln_model = ln_model
		self.max_num_routes = max_num_routes
		self.max_num_attempts_per_route = max_num_attempts_per_route
		self.max_route_length = max_route_length
		self.num_runs_per_simulation = num_runs_per_simulation

	def run_simulation_series(
		self,
		schedule_generation_function,
		duration,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		num_runs_per_simulation=None,
		normalize_results_for_duration=False):
		'''
			Run a series of simulations, iteration through ranges of upfront fee coefficient pairs.
		'''
		simulation_series_results = []
		self.normalize_results_for_duration = normalize_results_for_duration
		if num_runs_per_simulation is None:
			num_runs_per_simulation = self.num_runs_per_simulation
		total_num_simulations, simulation_num = len(upfront_base_coeff_range) * len(upfront_rate_coeff_range), 0
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				simulation_num += 1
				percent_done = round(100 * simulation_num / total_num_simulations)
				logger.debug(f"Starting simulation {simulation_num} / {total_num_simulations} ({percent_done} % done) with coeffs: base {upfront_base_coeff}, rate {upfront_rate_coeff}")
				self.ln_model.set_upfront_fee_from_coeff_for_all(upfront_base_coeff, upfront_rate_coeff)
				stats, revenues = self.run_simulation(schedule_generation_function, duration, num_runs_per_simulation, normalize_results_for_duration)
				result = {
					"upfront_base_coeff": upfront_base_coeff,
					"upfront_rate_coeff": upfront_rate_coeff,
					"stats": stats,
					"revenues": revenues
				}
				simulation_series_results.append(result)
		return simulation_series_results

	def run_simulation(self, schedule_generation_function, duration, num_runs_per_simulation, normalize_results_for_duration=False):
		'''
			Run a simulation self.num_runs_per_simulation times and average results.
		'''
		tmp_num_sent, tmp_num_failed, tmp_num_reached_receiver, tmp_num_hit_target_node = [], [], [], []
		tmp_revenues = defaultdict(list)
		for i in range(num_runs_per_simulation):
			logger.debug(f"Simulation {i + 1} of {num_runs_per_simulation}")
			# we can't generate schedules out of cycle because they get depleted during execution
			# (PriorityQueue does not support copying.)
			schedule = schedule_generation_function(duration)
			num_sent, num_failed, num_reached_receiver, num_hit_target_node = self.execute_schedule(schedule)
			logger.debug(f"Hit target node: {num_hit_target_node}")
			logger.debug(f"{num_sent} sent, {num_failed} failed, {num_reached_receiver} reached receiver, {num_hit_target_node} hit target")
			normalizer = duration if normalize_results_for_duration else 1

			def normalized(value):
				assert normalizer > 0
				return value if normalizer == 1 else value / normalizer
			tmp_num_sent.append(normalized(num_sent))
			tmp_num_failed.append(normalized(num_failed))
			tmp_num_reached_receiver.append(normalized(num_reached_receiver))
			tmp_num_hit_target_node.append(normalized(num_hit_target_node))
			for node in self.nodes_hit:
				tmp_revenues[node].append(normalized(
					self.ln_model.get_revenue(node, FeeType.UPFRONT)
					+ self.ln_model.get_revenue(node, FeeType.SUCCESS)))
		logger.debug(f"Average hit target node: {mean(tmp_num_hit_target_node)}")
		stats = {
			"num_sent": mean(tmp_num_sent),
			"num_failed": mean(tmp_num_failed),
			"num_reached_receiver": mean(tmp_num_reached_receiver),
			"num_hit_target_node": mean(tmp_num_hit_target_node)
		}
		revenues = dict.fromkeys(self.ln_model.hop_graph.nodes, 0)
		#logger.debug(f"Hit nodes: {self.nodes_hit}")
		for node in self.nodes_hit:
			revenues[node] = mean(tmp_revenues[node])
		return stats, revenues

	def reset(self):
		self.ln_model.reset_all_slots()
		self.ln_model.reset_all_revenues()
		self.now = -1
		self.num_sent_total, self.num_failed_total, self.num_reached_receiver_total = 0, 0, 0
		self.num_hit_target_node = 0
		self.routes_by_length = dict.fromkeys(range(self.max_route_length), 0)
		self.nodes_hit = set()

	def handle_event(self, event):
		raise NotImplementedError("handle_event must be implemented in a Simulator sub-class (such as HonestSimulator or JammingSimulator)")

	def execute_schedule(self, schedule):
		self.reset()
		self.schedule = schedule
		while not self.schedule.no_more_events():
			new_time, event = self.schedule.get_event()
			if new_time > self.now:
				logger.debug(f"Current time: {new_time}")
			if new_time > self.schedule.end_time:
				break
			self.now = new_time
			logger.debug(f"Got event: {event}")
			self.handle_event(event)
		if self.schedule.no_more_events():
			logger.debug(f"Depleted the schedule with end time {self.schedule.end_time}, last event was at {self.now}")
		else:
			logger.debug(f"Reached schedule end time {self.schedule.end_time}, last event was at {self.now}")
		self.now = self.schedule.end_time
		logger.debug(f"Finalizing in-flight HTLCs...")
		self.ln_model.finalize_in_flight_htlcs(self.now)
		logger.debug(f"Schedule executed: {self.num_sent_total} sent, {self.num_failed_total} failed, {self.num_reached_receiver_total} reached receiver")
		logger.debug(f"Total times hit target node: {self.num_hit_target_node}")
		return self.num_sent_total, self.num_failed_total, self.num_reached_receiver_total, self.num_hit_target_node

	def create_payment(self, route, amount, processing_delay, desired_result):
		p, u_nodes, d_nodes = None, route[:-1], route[1:]
		for u_node, d_node in reversed(list(zip(u_nodes, d_nodes))):
			logger.debug(f"Wrapping payment for fee policy from {u_node} to {d_node}")
			# Note: we model the sender's payment construction here
			# The sender can't check if a hop really can forward (i.e., is not jammed)
			# TODO: implement proper logic like: if the cheapest channel is jammed, choose another one
			# also note: this check is time-independent: we can check capacity and enabled status without time
			# only jamming status check is time-sensitive, but this is unavailable for us here
			chosen_ch = self.ln_model.get_hop(u_node, d_node).get_cheapest_channel_maybe_can_forward(Direction(u_node, d_node), amount)
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
				channel_in_direction=chosen_ch_in_dir,
				desired_result=desired_result if is_last_hop else None,
				processing_delay=processing_delay if is_last_hop else None,
				last_hop_body=amount if is_last_hop else None)
		return p


class JammingSimulator(Simulator):

	def __init__(
		self,
		ln_model,
		max_num_routes,
		max_num_attempts_per_route,
		num_runs_per_simulation,
		target_node_pairs,
		target_node=None,
		max_route_length=ProtocolParams["MAX_ROUTE_LENGTH"],
		max_target_node_pairs_per_route=None,
		jammer_must_route_via_nodes=[]):
		self.target_node_pairs = target_node_pairs
		self.target_node = target_node
		self.max_target_node_pairs_per_route = max_target_node_pairs_per_route if max_target_node_pairs_per_route is not None else max_route_length - 2
		self.jammer_must_route_via_nodes = jammer_must_route_via_nodes
		# we may not finish jamming a hop due to roll-back of the last looped jam
		# we can have at most as many unjammed slots as hops in the whole route
		# if needed, we jam it separately with no-repeated-hops-allowed route
		#max_default_routes_per_target_node_pair = 1 + ProtocolParams["MAX_ROUTE_LENGTH"]
		#max_num_routes = len(self.target_node_pairs) * max_default_routes_per_target_node_pair if max_num_routes is None else max_num_routes
		Simulator.__init__(self, ln_model, max_num_routes, max_num_attempts_per_route, max_route_length, num_runs_per_simulation)

	def run_simulation_series_without_extrapolation(
		self,
		schedule_generation_function,
		duration,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		num_runs_per_simulation=None,
		normalize_results_for_duration=False):
		'''
			Run a jamming-based simulation similar to how honest simulation is run:
			for each event, a new route is created, etc.
			This is technically correct but suboptimal, as all jams have the same value,
			and we don't take advantage of this during route creation.
		'''
		simulation_series_results = []
		if num_runs_per_simulation is None:
			num_runs_per_simulation = self.num_runs_per_simulation
		total_num_simulations, simulation_num = len(upfront_base_coeff_range) * len(upfront_rate_coeff_range), 0
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				simulation_num += 1
				percent_done = round(100 * simulation_num / total_num_simulations)
				logger.debug(f"Starting simulation {simulation_num} / {total_num_simulations} ({percent_done} % done) with coeffs: base {upfront_base_coeff}, rate {upfront_rate_coeff}")
				self.ln_model.set_upfront_fee_from_coeff_for_all(upfront_base_coeff, upfront_rate_coeff)
				stats, revenues = self.run_simulation(schedule_generation_function, duration, num_runs_per_simulation, normalize_results_for_duration)
				result = {
					"upfront_base_coeff": upfront_base_coeff,
					"upfront_rate_coeff": upfront_rate_coeff,
					"stats": stats,
					"revenues": revenues
				}
				simulation_series_results.append(result)
		return simulation_series_results

	def run_simulation_series_with_extrapolation(
		self,
		schedule_generation_function,
		duration,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		num_runs_per_simulation=None,
		normalize_results_for_duration=False):
		'''
			Run an optimized jamming-based simulation.
			A simulation is ran just once for _some_ non-zero success base coefficient.
			For all other upfront fee coefficients, revenues are re-scaled without running routing.
			Limitations and assumptions:
			- this only works for jams (i.e., no success-case fees are paid ever)
			- there is _some_ non-zero element in upfront base or upfront rate coefficients list
		'''
		simulation_series_results = []
		if num_runs_per_simulation is None:
			num_runs_per_simulation = self.num_runs_per_simulation
		non_zero_upfront_base_coeff = [base for base in upfront_base_coeff_range if base > 0]
		non_zero_upfront_rate_coeff = [rate for rate in upfront_rate_coeff_range if rate > 0]
		assert non_zero_upfront_base_coeff or non_zero_upfront_rate_coeff
		# we run the simulation just once, and scale the resulting revenue w.r.t base fees
		some_base_coeff = non_zero_upfront_base_coeff[0] if non_zero_upfront_base_coeff else 0
		some_rate_coeff = non_zero_upfront_rate_coeff[0] if non_zero_upfront_rate_coeff else 0
		logger.debug(f"Running one jamming simulation for extrapolation with upfront base / rate coeffs: {some_base_coeff}, {some_rate_coeff}")
		self.ln_model.set_upfront_fee_from_coeff_for_all(
			upfront_base_coeff=some_base_coeff, upfront_rate_coeff=some_rate_coeff)
		stats_some_coeff, revenues_some_coeff = self.run_simulation(schedule_generation_function, duration, num_runs_per_simulation, normalize_results_for_duration)
		logger.debug(f"Revenues for coeffs {some_base_coeff}, {some_rate_coeff}: {revenues_some_coeff}")
		# This is how much revenue each node gets when it forwards one jam.
		# We then scale it w.r.t. various upfront fee coefficients.
		# Note: success-fee is zero for all jams, so we don't have to account for it!
		# Caveat: revenue is not _exactly_ correct here because proportional part depends on where in the route the node is.
		# However, as both rates and jam amounts are low, we neglect this error.
		# It doesn't matter at all if upfront rate is zero, anyway.
		# Assumption: all success fees are the same (and equal to default).
		# This is important, as upfront base and rate are defined as proportion of their success-case counterparts.
		one_hit_upfront_fee = partial(lambda base, rate: ChannelInDirection.generic_fee_function(
			base=FeeParams["SUCCESS_BASE"] * base,
			rate=FeeParams["SUCCESS_RATE"] * rate,
			amount=ProtocolParams["DUST_LIMIT"]))
		one_hit_upfront_fee_some_coeffs = one_hit_upfront_fee(base=some_base_coeff, rate=some_rate_coeff)
		for upfront_base_coeff in upfront_base_coeff_range:
			for upfront_rate_coeff in upfront_rate_coeff_range:
				revenues = deepcopy(revenues_some_coeff)
				one_hit_upfront_fee_these_coeffs = one_hit_upfront_fee(base=upfront_base_coeff, rate=upfront_rate_coeff)
				revenue_scale = one_hit_upfront_fee_these_coeffs / one_hit_upfront_fee_some_coeffs
				revenues.update({node: revenues[node] * revenue_scale for node in revenues})
				result = {
					"upfront_base_coeff": upfront_base_coeff,
					"upfront_rate_coeff": upfront_rate_coeff,
					"stats": stats_some_coeff,
					"revenues": revenues
				}
				simulation_series_results.append(result)
		return simulation_series_results

	def run_simulation_series(
		self,
		schedule_generation_function,
		duration,
		upfront_base_coeff_range,
		upfront_rate_coeff_range,
		num_runs_per_simulation=None,
		normalize_results_for_duration=False,
		extrapolate_jamming_revenues=False):
		self.normalize_results_for_duration = normalize_results_for_duration
		run_simulation_series_function = (
			self.run_simulation_series_with_extrapolation if extrapolate_jamming_revenues
			else self.run_simulation_series_without_extrapolation)
		simulation_series_results = run_simulation_series_function(
			schedule_generation_function,
			duration,
			upfront_base_coeff_range,
			upfront_rate_coeff_range,
			num_runs_per_simulation,
			self.normalize_results_for_duration)
		return simulation_series_results

	def handle_event(self, event):
		logger.debug(f"Launching jam batch at time {self.now}")
		if self.jammer_must_route_via_nodes:
			self.send_jam_with_static_route(event)
		else:
			self.send_jam_with_router(event)
		next_batch_time = self.now + event.processing_delay
		if next_batch_time > self.schedule.end_time:
			logger.debug(f"Schedule time exceeded")
		else:
			logger.debug(f"Moving to the next jam batch")
			logger.debug(f"Pushing jam {event} into schedule for time {next_batch_time}")
			self.schedule.put_event(next_batch_time, event)

	def send_jam_with_static_route(self, event):
		rg = self.ln_model.routing_graph
		must_nodes = self.jammer_must_route_via_nodes
		assert(rg.has_edge("JammerSender", must_nodes[0]))
		assert(all(rg.has_edge(hop[0], hop[1]) for hop in zip(must_nodes, must_nodes[1:])))
		assert(rg.has_edge(must_nodes[-1], "JammerReceiver"))
		#route_from_sender = nx.shortest_path(rg, "JammerSender", must_nodes[0])
		#route_to_receiver = nx.shortest_path(rg, must_nodes[-1], "JammerReceiver")
		# FIXME: ensure that routes fit for jams here?
		route = ["JammerSender"] + must_nodes + ["JammerReceiver"]
		num_sent, num_failed, num_reached_receiver, last_node_reached, first_node_not_reached, num_hit_target_node = self.send_jam_via_route(event, route)
		assert(first_node_not_reached is not None)
		jammed_hop = (last_node_reached, first_node_not_reached)
		self.num_sent_total += num_sent
		self.num_failed_total += num_failed
		self.num_reached_receiver_total += num_reached_receiver
		self.num_hit_target_node += num_hit_target_node
		self.nodes_hit.update(route)
		logger.debug(f"Jammed hop {jammed_hop}")

	def all_target_node_pairs_are_really_jammed(self):
		return all(self.ln_model.get_hop(*hop).cannot_forward(Direction(*hop), self.now) for hop in self.target_node_pairs)

	def get_jammed_status_of_hops(self, hops):
		return [(
			Router.shorten_ids(hop),
			self.ln_model.get_hop(*hop).cannot_forward(Direction(*hop), self.now),
			self.ln_model.get_hop(*hop).get_total_num_slots_occupied_in_direction(Direction.Alph)
		) for hop in hops]

	def send_jam_with_router(self, event):
		#max_num_routes = self.max_num_routes
		target_node_pairs_unjammed = self.target_node_pairs.copy()
		router = Router(self.ln_model, event.amount, event.sender, event.receiver, self.max_target_node_pairs_per_route, self.max_route_length)
		router.update_route_generator(target_node_pairs_unjammed)
		num_route = 0
		while not self.all_target_node_pairs_are_really_jammed():
			num_route += 1
			logger.debug(f"Trying jamming route {num_route + 1} of max {self.max_num_routes}")
			logger.debug(f"At least {len(target_node_pairs_unjammed)} / {len(self.target_node_pairs)} target node pairs still unjammed")
			#logger.info(f"Trying to include up to {self.max_target_node_pairs_per_route} target node pairs in route of length {self.max_route_length}")
			if not target_node_pairs_unjammed:
				logger.debug(f"No unjammed target node pairs left, no need to try further routes")
				break
			try:
				route = router.get_route()
				logger.debug(f"Suggested route of length {len(route)}")
			except StopIteration:
				logger.warning(f"No route from {event.sender} to {event.receiver} via any of {target_node_pairs_unjammed}")
				break
			#logger.debug(f"Found route of length {len(route)}")
			num_sent, num_failed, num_reached_receiver, last_node_reached, first_node_not_reached, num_hit_target_node = self.send_jam_via_route(event, route)
			self.num_sent_total += num_sent
			self.num_failed_total += num_failed
			self.num_reached_receiver_total += num_reached_receiver
			self.num_hit_target_node += num_hit_target_node
			if first_node_not_reached is not None:
				jammed_hop = (last_node_reached, first_node_not_reached)
				logger.debug(f"Jammed hop {jammed_hop}")
				if "JammerSender" in jammed_hop or "JammerReceiver" in jammed_hop:
					logger.warning(f"Jammer's node is in a jammed hop {jammed_hop}. Assign more slots to the jammer!")
				assert(jammed_hop in target_node_pairs_unjammed or jammed_hop not in self.target_node_pairs)
				# Only if the newly jammed hop occurs in the route exactly once, can we be sure it's really jammed!
				# Otherwise, if the hop became jammed on a non-first occurrence in the route,
				# some slots would be freed up when the jam rolls back.
				# In that case, we don't exclude the hop from the list of unjammed hop, and move on to the next route.
				# The hop will be eventually jammed via some future (presumably non-looped) route.
				if Router.num_hop_occurs_in_path(jammed_hop, route) == 1:
					logger.debug(f"Removing {jammed_hop} from router (occurs only once in path)")
					router.remove_hop(jammed_hop)
					if jammed_hop in target_node_pairs_unjammed:
						logger.debug(f"Removing {jammed_hop} from unjammed hops {target_node_pairs_unjammed}")
						target_node_pairs_unjammed.remove(jammed_hop)
						router.update_route_generator(target_node_pairs_unjammed)
				else:
					logger.debug(f"Hop {jammed_hop} may not be fully jammed!")
					logger.debug(f"Jammed hop {jammed_hop} occurs {Router.num_hop_occurs_in_path(jammed_hop, route)} times in route {route}")
			else:
				logger.debug(f"All jams reached receiver for route {route}")
				#logger.debug(f"Allow for more attempts per route (now at {self.max_num_attempts_per_route})!")
				target_node_pairs_unjammed_in_this_route = [hop for hop in Router.get_hops(route) if (
					hop in self.target_node_pairs
					and self.ln_model.get_hop(*hop).can_forward(Direction(*hop), self.now)
				)]
				logger.debug(f"Target hops unjammed in this route: {self.get_jammed_status_of_hops(target_node_pairs_unjammed_in_this_route)}")
			logger.debug(f"All target node pairs jammed status: {self.get_jammed_status_of_hops(self.target_node_pairs)}")
		if not self.all_target_node_pairs_are_really_jammed():
			target_node_pairs_left_unjammed = [hop for hop in self.target_node_pairs if (
				self.ln_model.get_hop(*hop).can_forward(Direction(*hop), self.now)
			)]
			# sic! num_routes, not (num_routes + 1): though we start at zero, we count the last interation which breaks before producing a route
			logger.warning(f"Couldn't jam {len(target_node_pairs_left_unjammed)} target node pairs after {num_route} routes at time {self.now}.")
			logger.warning(f"Unjammed target node pairs: {self.get_jammed_status_of_hops(target_node_pairs_left_unjammed)}")
			#exit()
		else:
			logger.debug(f"All target node pairs are jammed at time {self.now}")

	def send_jam_via_route(self, event, route):
		assert(event.desired_result is False)
		logger.debug(f"Sending jam via {route}")
		logger.debug(f"Receiver will get {event.amount} in payment body")
		p = self.create_payment(route, event.amount, event.processing_delay, event.desired_result)
		num_sent, num_failed, num_reached_receiver, num_hit_target_node = 0, 0, 0, 0
		for attempt_num in range(self.max_num_attempts_per_route):
			reached_receiver, last_node_reached, first_node_not_reached, error_type, nodes_hit_count = self.ln_model.attempt_send_payment(
				p,
				event.sender,
				self.now,
				attempt_num)
			assert(error_type is not None)
			num_sent += 1
			num_hit_target_node += nodes_hit_count[self.target_node] if self.target_node is not None else 0
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
		self.nodes_hit.update(route)
		return num_sent, num_failed, num_reached_receiver, last_node_reached, first_node_not_reached, num_hit_target_node


class HonestSimulator(Simulator):

	def __init__(
		self,
		ln_model,
		max_num_routes,
		max_num_attempts_per_route,
		num_runs_per_simulation,
		max_route_length=ProtocolParams["MAX_ROUTE_LENGTH"],
		subtract_last_hop_upfront_fee_for_honest_payments=True):
		self.subtract_last_hop_upfront_fee_for_honest_payments = subtract_last_hop_upfront_fee_for_honest_payments
		Simulator.__init__(self, ln_model, max_num_routes, max_num_attempts_per_route, max_route_length, num_runs_per_simulation)

	def handle_event(self, event):
		return self.send_honest_payment(event)

	def send_honest_payment(self, event):
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
			for num_route in range(self.max_num_routes):
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

	def send_honest_payment_via_route(self, event, route):
		assert event.desired_result is True
		if self.subtract_last_hop_upfront_fee_for_honest_payments:
			last_hop_body = self.adjust_body_for_route(route, event.amount)
		else:
			last_hop_body = event.amount
		logger.debug(f"Receiver will get {last_hop_body} in payment body")
		p = self.create_payment(route, last_hop_body, event.processing_delay, event.desired_result)
		num_sent, num_failed, num_reached_receiver = 0, 0, 0
		for attempt_num in range(self.max_num_attempts_per_route):
			reached_receiver, last_node_reached, first_node_not_reached, error_type, nodes_hit_count = self.ln_model.attempt_send_payment(
				p,
				event.sender,
				self.now,
				attempt_num)
			num_sent += 1
			if reached_receiver:
				logger.debug(f"Payment reached the receiver after {attempt_num + 1} attempts")
				num_reached_receiver += 1
				break
			elif error_type is not None:
				logger.debug(f"Payment failed at {last_node_reached}-{first_node_not_reached} with {error_type} at attempt {attempt_num}")
				num_failed += 1
		self.nodes_hit.update(route)
		return num_sent, num_failed, num_reached_receiver

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
		return HonestSimulator.body_for_amount(amount, chosen_ch_in_dir.upfront_fee_function)

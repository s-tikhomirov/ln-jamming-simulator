from math import isclose, floor
import json

from direction import Direction
from simulator import JammingSimulator, HonestSimulator
from event import Event
from schedule import GenericSchedule, HonestSchedule
from lnmodel import LNModel
from enumtypes import FeeType, ErrorType

import logging
logger = logging.getLogger(__name__)

TEST_SNAPSHOT_FILENAME = "./snapshots/listchannels_test.json"
# Initially, the only test route was Alice - Bob - Charlie - Dave.
# We renamed Bob to Mary to test that everything works if route is not alphabetically ordered.
# (We kept b_ variable names though.)

DEFAULT_NUM_SLOTS_PER_CHANNEL_IN_DIRECTION = 2


def get_example_ln_model():
	with open(TEST_SNAPSHOT_FILENAME, 'r') as snapshot_file:
		snapshot_json = json.load(snapshot_file)
	return LNModel(snapshot_json, default_num_slots_per_channel_in_direction=DEFAULT_NUM_SLOTS_PER_CHANNEL_IN_DIRECTION, no_balance_failures=True)


def get_example_j_sim():
	ln_model = get_example_ln_model()
	sim = JammingSimulator(
		ln_model,
		target_hops=[("Mary", "Charlie")],
		max_num_routes=1,
		max_num_attempts_per_route=500,
		num_runs_per_simulation=1)
	return sim


def get_example_h_sim():
	ln_model = get_example_ln_model()
	sim = HonestSimulator(
		ln_model,
		max_num_routes=1,
		max_num_attempts_per_route=1,
		num_runs_per_simulation=1,
		subtract_last_hop_upfront_fee_for_honest_payments=False)
	return sim


def test_no_routes():
	with open(TEST_SNAPSHOT_FILENAME, 'r') as snapshot_file:
		snapshot_json = json.load(snapshot_file)
	del snapshot_json["channels"][1]
	ln_model = LNModel(snapshot_json, default_num_slots_per_channel_in_direction=2, no_balance_failures=True)
	sim = HonestSimulator(
		ln_model,
		max_num_attempts_per_route=1,
		max_num_routes=1,
		num_runs_per_simulation=1,
		subtract_last_hop_upfront_fee_for_honest_payments=False)
	sch = GenericSchedule(duration=1)
	sch.put_event(0, Event("Alice", "Dave", 100, 7, False))
	sch.put_event(0, Event("Alice", "Dave", 100, 7, True))
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent == 0)


def test_not_enough_attempts():
	sim = JammingSimulator(
		get_example_ln_model(),
		target_hops=[("Mary", "Charlie")],
		max_num_attempts_per_route=1,
		max_num_routes=1,
		num_runs_per_simulation=1)
	sch = GenericSchedule(duration=1)
	sch.put_event(0, Event("Alice", "Dave", 100, 7, False))
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent == 1)
	assert(num_sent == num_failed == num_reached_receiver)


def test_jammer_jammed():
	ln_model = get_example_ln_model()
	ln_model.add_jammers_channels(send_to_nodes=["Alice"], num_slots=1)
	sim = JammingSimulator(
		ln_model,
		target_hops=[("Charlie", "Dave")],
		max_num_attempts_per_route=500,
		max_num_routes=1,
		num_runs_per_simulation=1)
	sch = GenericSchedule(duration=1)
	sch.put_event(0, Event("JammerSender", "Dave", 100, 7, False))
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent == 2)
	assert(num_failed == 2)
	assert(num_reached_receiver == 1)


def test_simulator_one_successful_payment():
	sim = get_example_h_sim()
	sch = GenericSchedule(duration=10)
	event = Event("Alice", "Dave", 100, 1, True)
	sch.put_event(0, event)
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	#example_simulator.ln_model.report_revenues()
	assert(num_sent == 1)
	assert(num_failed == 0)
	assert(num_reached_receiver == 1)
	assert_final_revenue_correctness(sim, num_sent)
	# Now we make specific tests; Dave's revenues are zero by construction (tested above)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", FeeType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", FeeType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Mary", FeeType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Mary", FeeType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", FeeType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", FeeType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", FeeType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", FeeType.SUCCESS)
	# The following holds for these fee policies (success / upfront):
	# A-B: 6+6% / 5+5%
	# B-C: 4+4% / 3+3%
	# C-D: 2+2% / 1+1%
	assert(isclose(a_rev_upfront, -19.664))
	assert(isclose(a_rev_success, -20.48))
	assert(isclose(b_rev_upfront, 11.424))
	assert(isclose(b_rev_success, 12.48))
	assert(isclose(c_rev_upfront, 6.24))
	assert(isclose(c_rev_success, 8))
	assert(isclose(d_rev_upfront, 2))
	assert(isclose(d_rev_success, 0))
	# Total amounts must sum to zero: money doesn't appear or disappear
	# Moreover, as success- and upfront fees are separated, they individually sum to zero.
	# Use math.isclose() to avoid comparing floats for equality (rounding issues).
	# Note: this is only true if no htlcs are left in-flight!
	assert(isclose(a_rev_upfront + b_rev_upfront + c_rev_upfront + d_rev_upfront, 0))
	assert(isclose(a_rev_success + b_rev_success + c_rev_success + d_rev_success, 0))


def test_simulator_one_jam_batch():
	sim = get_example_j_sim()
	sch = GenericSchedule(duration=1)
	sch.put_event(0, Event("Alice", "Dave", 100, 7, False))
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent == 3)
	assert(num_failed == 3)
	assert(num_reached_receiver == 2)
	# the third jam fails because of lack of slots at the first hop
	assert_final_revenue_correctness(sim, num_sent)
	# Now we make specific tests; JammerReceiver's revenues are zero by construction (tested above)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", FeeType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", FeeType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Mary", FeeType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Mary", FeeType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", FeeType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", FeeType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", FeeType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", FeeType.SUCCESS)
	# The following holds for these fee policies (success / upfront):
	# A-B: 6+6% / 5+5%
	# B-C: 4+4% / 3+3%
	# C-D: 2+2% / 1+1%
	# Alice is the first to run out of slots, hence a warning in logs is OK
	# (in the real simulations, we would want to allocate more slots to the sender)
	assert(isclose(a_rev_upfront, - 19.664 * 2))
	assert(isclose(b_rev_upfront, 11.424 * 2))
	assert(isclose(c_rev_upfront, 6.24 * 2))
	assert(isclose(d_rev_upfront, 2 * 2))
	assert(a_rev_success == b_rev_success == c_rev_success == d_rev_success == 0)


def test_simulator_end_htlc_resolution():
	sim = HonestSimulator(
		get_example_ln_model(),
		max_num_attempts_per_route=1,
		max_num_routes=1,
		num_runs_per_simulation=1,
		subtract_last_hop_upfront_fee_for_honest_payments=False)
	sch = GenericSchedule(duration=10)
	sch.put_event(0, Event("Alice", "Dave", 100, 5, True))
	sch.put_event(0, Event("Alice", "Dave", 100, 15, True))
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent == 2)
	# the first payment succeeded, the second was in-flight at cutoff time
	# it has neither succeeded nor failed
	assert(num_failed == 0)
	assert(num_reached_receiver == 2)
	# Compared to one successful payment:
	# success-case revenues don't change; upfront revenues are twice as high
	assert_final_revenue_correctness(sim, num_sent)
	# Now we make specific tests; Dave's revenues are zero by construction (tested above)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", FeeType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", FeeType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Mary", FeeType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Mary", FeeType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", FeeType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", FeeType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", FeeType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", FeeType.SUCCESS)
	# The following holds for these fee policies (success / upfront):
	# A-B: 6+6% / 5+5%
	# B-C: 4+4% / 3+3%
	# C-D: 2+2% / 1+1%
	assert(isclose(a_rev_upfront, -19.664 * 2))
	assert(isclose(a_rev_success, -20.48))
	assert(isclose(b_rev_upfront, 11.424 * 2))
	assert(isclose(b_rev_success, 12.48))
	assert(isclose(c_rev_upfront, 6.24 * 2))
	assert(isclose(c_rev_success, 8))
	assert(isclose(d_rev_upfront, 2 * 2))
	assert(isclose(d_rev_success, 0))
	#example_ln_model.report_revenues()


def test_simulator_with_random_schedule():
	sim = get_example_h_sim()
	sch = HonestSchedule(
		duration=60,
		senders=["Alice"],
		receivers=["Dave"])
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent > 0)
	assert_final_revenue_correctness(sim, num_sent)
	#example_simulator.ln_model.report_revenues()


def test_simulator_jamming():
	# FIXME: set jammer's channels properly
	sim = JammingSimulator(
		get_example_ln_model(),
		target_hops=[("Mary", "Charlie")],
		max_num_attempts_per_route=500,
		max_num_routes=1,
		num_runs_per_simulation=1)
	for (x, y) in (("Alice", "Mary"), ("Charlie", "Dave")):
		for ch in sim.ln_model.get_hop(x, y).get_all_channels():
			ch.reset_slots_in_direction(Direction(x, y), num_slots=100)
	duration = 10
	sch = GenericSchedule(duration)
	jam_processing_delay = 4
	sch.put_event(0, Event("Alice", "Dave", 100, jam_processing_delay, False))
	sim.target_node_pair = (("Mary", "Charlie"))
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", FeeType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", FeeType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Mary", FeeType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Mary", FeeType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", FeeType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", FeeType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", FeeType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", FeeType.SUCCESS)
	# The following holds for these fee policies (success / upfront):
	# A-B: 6+6% / 5+5%
	# B-C: 4+4% / 3+3%
	# C-D: 2+2% / 1+1%
	# We expect 3 batches of 3 jams each (at times 0, 4, 8).
	# Two jams per batch reach the receiver, the third fails at B indicating that the victim is jammed.
	# Therefore, A pays to B 9x upfront fee, while B pays to C, and C pays to D, 6x upfront fee.
	assert(num_sent == 9)
	assert(num_failed == num_sent)
	assert(num_reached_receiver == 6)
	assert_final_revenue_correctness(sim, num_sent)
	assert(isclose(a_rev_upfront, -19.664 * 9))
	assert(isclose(b_rev_upfront, 19.664 * 9 - 8.24 * 6))
	assert(isclose(c_rev_upfront, 8.24 * 6 - 2 * 6))
	assert(isclose(d_rev_upfront, 2 * 6))
	assert(a_rev_success == b_rev_success == c_rev_success == d_rev_success == 0)
	#example_ln_model.report_revenues()


def assert_final_revenue_correctness(sim, num_sent):
	a_rev_upfront = sim.ln_model.get_revenue("Alice", FeeType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", FeeType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Mary", FeeType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Mary", FeeType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", FeeType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", FeeType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", FeeType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", FeeType.SUCCESS)

	# Alice only sends payments; her total revenue is negative
	# (assuming non-zero fees)
	# Although individual revenue components may be zero.
	assert(a_rev_upfront <= 0)
	assert(a_rev_success <= 0)
	assert(a_rev_upfront + a_rev_success < 0 or num_sent == 0)

	# Mary and Charlie are routing nodes; their revenues are non-negative
	assert(b_rev_upfront >= 0)
	assert(c_rev_upfront >= 0)
	assert(b_rev_success >= 0)
	assert(c_rev_success >= 0)

	# Dave is the receiver; his success-case revenue is zero by construction
	assert(d_rev_success == 0)
	assert(d_rev_upfront >= 0)


def test_body_for_amount_function():
	target_amount = 1000

	def upfront_fee_function(a):
		return 0.01 * a + 5
	adjusted_amount = HonestSimulator.body_for_amount(target_amount, upfront_fee_function)
	# 986 * 0.01 + 5 = 9.86 + 5 = 14.86
	# 986 + 14.86 = 1000.986
	assert(adjusted_amount == 986)

	adjusted_amount = HonestSimulator.body_for_amount(
		target_amount,
		upfront_fee_function,
		max_steps=3)
	assert(adjusted_amount == 875)


def test_error_response_honest():
	sim = HonestSimulator(
		get_example_ln_model(),
		max_num_attempts_per_route=1,
		max_num_routes=1,
		num_runs_per_simulation=1,
		subtract_last_hop_upfront_fee_for_honest_payments=False)
	# an honest payment gets retried multiple times but still fails
	for ch in sim.ln_model.get_hop("Mary", "Charlie").get_all_channels():
		ch.set_deliberate_failure_behavior_in_direction(Direction("Mary", "Charlie"), prob=1)
	sch = GenericSchedule()
	event = Event("Alice", "Dave", 100, 1, True)
	sch.put_event(0, event)
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	assert(num_sent == sim.max_num_routes * sim.max_num_attempts_per_route)
	assert(num_failed == num_sent)
	assert(num_reached_receiver == 0)


def test_error_response_jamming():
	sim = JammingSimulator(
		get_example_ln_model(),
		target_hops=[("Mary", "Charlie")],
		max_num_attempts_per_route=500,
		max_num_routes=1,
		num_runs_per_simulation=1)
	for ch in sim.ln_model.get_hop("Mary", "Charlie").get_all_channels():
		ch.set_deliberate_failure_behavior_in_direction(Direction("Mary", "Charlie"), prob=1, spoofing_error_type=ErrorType.LOW_BALANCE)
	for (x, y) in (("Alice", "Mary"), ("Charlie", "Dave")):
		for ch in sim.ln_model.get_hop(x, y).get_all_channels():
			ch.reset_slots_in_direction(Direction(x, y), num_slots=100)
	duration = 4
	max_num_attempts_per_route = 10
	sch = GenericSchedule(duration)
	sim.target_node_pair = (("Mary", "Charlie"))
	sim.max_num_attempts_per_route = max_num_attempts_per_route
	jam_processing_delay = 4
	event = Event("Alice", "Dave", 100, jam_processing_delay, False)
	sch.put_event(0, event)
	logger.debug("Start executing schedule")
	num_sent, num_failed, num_reached_receiver, num_hit_target_node = sim.execute_schedule(sch)
	logger.debug("Finished executing schedule")
	assert(num_sent == (1 + floor(duration / jam_processing_delay)) * max_num_attempts_per_route)
	assert(num_failed == num_sent)
	assert(num_reached_receiver == 0)

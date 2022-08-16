from math import isclose
import json
import pytest

from simulator import Simulator, body_for_amount
from schedule import Schedule, Event
from lnmodel import LNModel, RevenueType
from params import honest_amount_function, honest_proccesing_delay_function, honest_generation_delay_function

TEST_SNAPSHOT_FILENAME = "./snapshots/listchannels_test.json"

@pytest.fixture
def example_ln_model():
	with open(TEST_SNAPSHOT_FILENAME, 'r') as snapshot_file:
		snapshot_json = json.load(snapshot_file)
	return LNModel(snapshot_json, default_num_slots=2)

def test_simulator_one_successful_payment(example_ln_model):
	sim = Simulator(example_ln_model)
	sch = Schedule()
	event = Event("Alice", "Dave", 100, 1, True)
	sch.put_event(0, event)
	num_events, num_failed = sim.execute_schedule(sch, simulation_cutoff=10,
		enforce_dust_limit=False,
		no_balance_failures=True,
		subtract_last_hop_upfront_fee_for_honest_payments=False,
		keep_receiver_upfront_fee=True)
	#example_ln_model.report_revenues()
	assert(num_events == 1)
	assert(num_failed == 0)
	assert_final_revenue_correctness(sim, num_events)
	# Now we make specific tests; Dave's revenues are zero by construction (tested above)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", RevenueType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", RevenueType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Bob", RevenueType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Bob", RevenueType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", RevenueType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", RevenueType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", RevenueType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", RevenueType.SUCCESS)
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

def test_simulator_one_jam(example_ln_model):
	sim = Simulator(example_ln_model)
	sch = Schedule()
	event = Event("Alice", "Dave", 100, 1, False)
	sch.put_event(0, event)
	num_events, num_failed = sim.execute_schedule(sch,
		simulation_cutoff=2,
		enforce_dust_limit=False,
		no_balance_failures=True,
		subtract_last_hop_upfront_fee_for_honest_payments=False,
		keep_receiver_upfront_fee=True)
	assert(num_events == 1)
	assert(num_failed == 1)
	#example_ln_model.report_revenues()
	assert_final_revenue_correctness(sim, num_events)
	# Now we make specific tests; Dave's revenues are zero by construction (tested above)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", RevenueType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", RevenueType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Bob", RevenueType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Bob", RevenueType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", RevenueType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", RevenueType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", RevenueType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", RevenueType.SUCCESS)
	# The following holds for these fee policies (success / upfront):
	# A-B: 6+6% / 5+5%
	# B-C: 4+4% / 3+3%
	# C-D: 2+2% / 1+1%
	assert(isclose(a_rev_upfront, -19.664))
	assert(isclose(b_rev_upfront, 11.424))
	assert(isclose(c_rev_upfront, 6.24))
	assert(isclose(d_rev_upfront, 2))
	assert(a_rev_success == b_rev_success == c_rev_success == d_rev_success == 0)

def test_simulator_end_htlc_resolution(example_ln_model):
	sim = Simulator(example_ln_model)
	sch = Schedule()
	event1 = Event("Alice", "Dave", 100, 5, True)
	event2 = Event("Alice", "Dave", 100, 15, True)
	sch.put_event(0, event1)
	sch.put_event(0, event2)
	num_events, num_failed = sim.execute_schedule(sch,
		simulation_cutoff=10,
		enforce_dust_limit=False,
		no_balance_failures=True,
		subtract_last_hop_upfront_fee_for_honest_payments=False,
		keep_receiver_upfront_fee=True)
	assert(num_events == 2)
	# the first payment succeeded, the second was in-flight at cutoff time
	# it has neither succeeded nor failed
	assert(num_failed == 0)
	# Compared to one successful payment:
	# success-case revenues don't change; upfront revenues are twice as high
	assert_final_revenue_correctness(sim, num_events)
	# Now we make specific tests; Dave's revenues are zero by construction (tested above)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", RevenueType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", RevenueType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Bob", RevenueType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Bob", RevenueType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", RevenueType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", RevenueType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", RevenueType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", RevenueType.SUCCESS)
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

def test_simulator_with_random_schedule(example_ln_model):
	sim = Simulator(example_ln_model)
	sch = Schedule()
	scheduled_duration = 60
	sch.generate_schedule(
		senders_list = ["Alice"],
		receivers_list = ["Dave"],
		amount_function = honest_amount_function,
		desired_result = True,
		payment_processing_delay_function = honest_proccesing_delay_function,
		payment_generation_delay_function = honest_generation_delay_function,
		scheduled_duration = scheduled_duration)
	num_events, num_failed = sim.execute_schedule(sch,
		simulation_cutoff=scheduled_duration,
		no_balance_failures=True,
		keep_receiver_upfront_fee=True)
	assert(num_events > 0)
	assert_final_revenue_correctness(sim, num_events)
	#example_ln_model.report_revenues()

def test_simulator_jamming(example_ln_model):
	sim = Simulator(example_ln_model)
	example_ln_model.set_num_slots("Alice", "Bob", 100)
	example_ln_model.set_num_slots("Charlie", "Dave", 100)
	sch = Schedule()
	jam_processing_delay = 4
	simulation_cutoff = 10
	sch.put_event(0, Event("Alice", "Dave", 100, jam_processing_delay, False))
	num_events, num_failed = sim.execute_schedule(sch,
		target_node_pair=("Bob", "Charlie"),
		jam_with_insertion=True,
		simulation_cutoff=simulation_cutoff,
		enforce_dust_limit=False,
		no_balance_failures=True,
		subtract_last_hop_upfront_fee_for_honest_payments=False,
		keep_receiver_upfront_fee=True)
	a_rev_upfront = sim.ln_model.get_revenue("Alice", RevenueType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", RevenueType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Bob", RevenueType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Bob", RevenueType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", RevenueType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", RevenueType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", RevenueType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", RevenueType.SUCCESS)
	# The following holds for these fee policies (success / upfront):
	# A-B: 6+6% / 5+5%
	# B-C: 4+4% / 3+3%
	# C-D: 2+2% / 1+1%
	# We expect 3 batches of 3 jams each (at times 0, 4, 8).
	# Two jams per batch reach the receiver, the third fails at B indicating that the victim is jammed.
	# Therefore, A pays to B 9x upfront fee, while B pays to C, and C pays to D, 6x upfront fee.
	assert(num_events == 9)
	assert(num_failed == num_events)
	assert_final_revenue_correctness(sim, num_events)
	assert(isclose(a_rev_upfront, -19.664 * 9))
	assert(isclose(b_rev_upfront, 19.664 * 9 - 8.24 * 6))
	assert(isclose(c_rev_upfront, 8.24 * 6 - 2 * 6))
	assert(isclose(d_rev_upfront, 2 * 6))
	assert(a_rev_success == b_rev_success == c_rev_success == d_rev_success == 0)
	#example_ln_model.report_revenues()

def assert_final_revenue_correctness(sim, num_events):
	a_rev_upfront = sim.ln_model.get_revenue("Alice", RevenueType.UPFRONT)
	a_rev_success = sim.ln_model.get_revenue("Alice", RevenueType.SUCCESS)
	b_rev_upfront = sim.ln_model.get_revenue("Bob", RevenueType.UPFRONT)
	b_rev_success = sim.ln_model.get_revenue("Bob", RevenueType.SUCCESS)
	c_rev_upfront = sim.ln_model.get_revenue("Charlie", RevenueType.UPFRONT)
	c_rev_success = sim.ln_model.get_revenue("Charlie", RevenueType.SUCCESS)
	d_rev_upfront = sim.ln_model.get_revenue("Dave", RevenueType.UPFRONT)
	d_rev_success = sim.ln_model.get_revenue("Dave", RevenueType.SUCCESS)

	# Alice only sends payments; her total revenue is negative
	# (assuming non-zero fees)
	# Although individual revenue components may be zero.
	assert(a_rev_upfront <= 0)
	assert(a_rev_success <= 0)
	### The following is true after _any_ simulation with at least one 
	assert(a_rev_upfront + a_rev_success < 0 or num_events == 0)

	# Bob and Charlie are routing nodes; their revenues are non-negative
	assert(b_rev_upfront >= 0)
	assert(c_rev_upfront >= 0)
	# this may not hold if upstream is cheap but downstream is expensive!
	# in other words, it rates (sharply) increase downstream, 
	# a router may lost on success-case fees.
	# It does gain on upfront fees in any case.
	# It's a separate question to check if the total is positive - not guaranteed.
	#assert(b_rev_success >= 0)
	assert(c_rev_success >= 0)

	# Dave is the receiver; his success-case revenue is zero by construction
	assert(d_rev_success == 0)
	# Upfront fee amount has been subtracted at payment construction,
	# but in this test we keep it (keep_receiver_upfront_fee=True)
	# to later assert that the sum of all fees is zero.
	# assert(d_rev_upfront == 0)


def test_body_for_amount_function():
	target_amount = 1000
	upfront_fee_function = lambda a : 0.01 * a + 5
	adjusted_amount = body_for_amount(target_amount, upfront_fee_function)
	# 986 * 0.01 + 5 = 9.86 + 5 = 14.86
	# 986 + 14.86 = 1000.986
	assert(adjusted_amount == 986)


def test_error_response(example_ln_model):
	# an honest payment gets retried multiple times but still fails
	example_ln_model.set_deliberate_failure_behavior("Bob", "Charlie", 1)
	sim = Simulator(example_ln_model)
	sch = Schedule()
	event = Event("Alice", "Dave", 100, 1, True)
	sch.put_event(0, event)
	num_events, num_failed = sim.execute_schedule(sch,
		simulation_cutoff=2,
		enforce_dust_limit=False,
		no_balance_failures=True,
		subtract_last_hop_upfront_fee_for_honest_payments=False,
		keep_receiver_upfront_fee=True,
		num_attempts_for_honest_payments=5)
	assert(num_events == 1)
	assert(num_failed == num_events)
	
#!/usr/bin/env python3

import csv
import statistics
import time

from node import Node
from payment import Payment, HonestPaymentGenerator, JamPaymentGenerator
from fee import LinearFeePolicy

# Parameters for fee calculation
BASE_FEE 			= 500
PROP_FEE_SHARE 		= 0.01
#UPFRONT_FEE_SHARE 	= 0

# Parameters for payment generation
K = 1000
MIN_AMOUNT = 1 * K
MAX_AMOUNT = 1000 * K
MIN_DELAY = 1
EXPECTED_EXTRA_DELAY = 10

#PROB_FAIL = 0.1
# we expect an honest payment every X seconds on average
# in terms of exponential distribution, this is beta (aka scale, aka the inverse of rate lambda)
#HONEST_PAYMENT_EVERY_SECONDS = 30

DUST_LIMIT = 10000
JAM_DELAY = MIN_DELAY + 2 * EXPECTED_EXTRA_DELAY

SIMULATION_DURATION = 60*60
NUM_SLOTS = 10

def run_simulation(route, payment_generator):
	elapsed = 0
	while elapsed < SIMULATION_DURATION:
		payment_batch, time_to_next = payment_generator.next(route, num_payments_in_batch=NUM_SLOTS)
		elapsed += time_to_next
		success_so_far = True
		for node in route:
			success_so_far = node.handle(payment_batch)
			if not success_so_far:
				# payment has failed (no slot at next node)
				break
		for node in route:
			node.update_slot_leftovers(time_to_next)

def average_fee_revenue(route, pg, num_simulations):
	revenues = []
	for num_simulation in range(num_simulations):
		run_simulation(route, pg)
		revenues.append(route[1].revenue)
		for node in route:
			node.reset()
	return statistics.mean(revenues)

def setup_route(base_fee, prop_fee_share, upfront_fee_share):
	fp = LinearFeePolicy(base_fee, prop_fee_share, upfront_fee_share)
	route = [Node("Alice", fp, NUM_SLOTS), Node("Bob", fp, NUM_SLOTS), Node("Charlie", fp, NUM_SLOTS)]
	for node in route:
		node.set_fee_policy(fp)
	return route

def run_simulations(num_simulations, upfront_fee_share_steps):
	timestamp = str(int(time.time()))
	upfront_fee_share_range = [x/upfront_fee_share_steps for x in range(upfront_fee_share_steps+1)]
	honest_payment_every_seconds_range = [30]
	prob_fail_range = [x/10 for x in range(11)]
	break_even_upfront_fee_shares = []
	with open("results/" + timestamp + "-revenues" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["prob_fail", "honest_payment_every_seconds", "upfront_fee_share", 
			"normal_revenue", "jamming_revenue", "jamming_revenue_is_higher"])
		print("Running simulations with different value for parameters")
		num_comb = len(prob_fail_range) * len(honest_payment_every_seconds_range) * len(upfront_fee_share_range)
		print("Total parameter combinations:", num_comb)
		print(prob_fail_range, honest_payment_every_seconds_range, upfront_fee_share_range)
		print("prob_fail, honest_payment_every_seconds, upfront_fee_share")
		for prob_fail in prob_fail_range:
			for honest_payment_every_seconds in honest_payment_every_seconds_range:
				break_even_reached = False
				for upfront_fee_share in upfront_fee_share_range:
					print(prob_fail, honest_payment_every_seconds, upfront_fee_share)
					route = setup_route(BASE_FEE, PROP_FEE_SHARE, upfront_fee_share)
					pg = HonestPaymentGenerator(route, MIN_AMOUNT, MAX_AMOUNT, MIN_DELAY, EXPECTED_EXTRA_DELAY,
						prob_fail, honest_payment_every_seconds)
					r = average_fee_revenue(route, pg, num_simulations)
					jam_pg = JamPaymentGenerator(route, DUST_LIMIT, JAM_DELAY)
					r_jam = average_fee_revenue(route, jam_pg, num_simulations)
					if r < r_jam and not break_even_reached:
						break_even_reached = True
						break_even_upfront_fee_shares.append([prob_fail, honest_payment_every_seconds, upfront_fee_share])
					writer.writerow([prob_fail, honest_payment_every_seconds,
						"%.2f" % upfront_fee_share, 
						round(r), round(r_jam), break_even_reached])
				if not break_even_reached:
					break_even_upfront_fee_shares.append([prob_fail, honest_payment_every_seconds, None])
	with open("results/" + timestamp + "-breakeven" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["prob_fail", "honest_payment_every_seconds", "breakeven_upfront_fee_share"])
		for line in break_even_upfront_fee_shares:
			writer.writerow(line)


def main():
	run_simulations(num_simulations=100, upfront_fee_share_steps=10)


if __name__ == "__main__":
	main()

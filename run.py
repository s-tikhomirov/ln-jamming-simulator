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
MAX_AMOUNT = 100 * K
MIN_DELAY = 1
EXPECTED_EXTRA_DELAY = 10

#PROB_FAIL = 0.1
# we expect an honest payment every X seconds on average
# in terms of exponential distribution, this is beta (aka scale, aka the inverse of rate lambda)
#HONEST_PAYMENT_EVERY_SECONDS = 30

DUST_LIMIT = 100000
JAM_DELAY = MIN_DELAY + 2 * EXPECTED_EXTRA_DELAY

SIMULATION_DURATION = 60*60*24


def run_simulation(route, payment_generator):
	# FIXME: should this logic be in the Node class?
	elapsed = 0 		# total simulated time elapsed since simulation started
	leftover = 0 		# time to process past payments "carried over" to next payment cycles
	num_skipped = 0 	# number of payments skipped (due to handling other payments)
	num_payments = 0 	# total number of payments received (not necessarily handled)
	while elapsed < SIMULATION_DURATION:
		payment, time_to_next = payment_generator.next(route)
		num_payments += 1
		elapsed += time_to_next
		if leftover > 0:
			# previous payment is still being handled
			num_skipped += 1
			leftover = max(0, leftover - time_to_next)
		else:
			# handle new payment
			for node in route:
				node.handle(payment)
			leftover = max(0, payment.delay - time_to_next)
	#print("Skipped", num_skipped, " / ", num_payments, "or", round(num_skipped / num_payments, 2), "of payments.")


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
	route = [Node("Alice", fp), Node("Bob", fp), Node("Charlie", fp)]
	for node in route:
		node.set_fee_policy(fp)
	return route

def run_simulations(num_simulations, upfront_fee_share_steps):
	upfront_fee_share_range = [x/upfront_fee_share_steps for x in range(upfront_fee_share_steps+1)]
	honest_payment_every_seconds_range = [10,20,30]
	prob_fail_range = [x/10 for x in range(11)]
	with open("results/results-" + str(int(time.time())) +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["prob_fail", "honest_payment_every_seconds", "upfront_fee_share", 
			"normal_revenue", "jamming_revenue", "jamming_revenue_is_higher"])
		print("Running simulations with different value for parameters")
		print("Total parameter combinations:", 
			len(prob_fail_range) * len(honest_payment_every_seconds_range) * len(upfront_fee_share_range))
		print(prob_fail_range, honest_payment_every_seconds_range, upfront_fee_share_range)
		print("prob_fail, honest_payment_every_seconds, upfront_fee_share")
		for prob_fail in prob_fail_range:
			for honest_payment_every_seconds in honest_payment_every_seconds_range:
				for upfront_fee_share in upfront_fee_share_range:
					print(prob_fail, honest_payment_every_seconds, upfront_fee_share)
					route = setup_route(BASE_FEE, PROP_FEE_SHARE, upfront_fee_share)
					pg = HonestPaymentGenerator(route, MIN_AMOUNT, MAX_AMOUNT, MIN_DELAY, EXPECTED_EXTRA_DELAY,
						prob_fail, honest_payment_every_seconds)
					r = average_fee_revenue(route, pg, num_simulations)
					jam_pg = JamPaymentGenerator(route, DUST_LIMIT, JAM_DELAY)
					r_jam = average_fee_revenue(route, jam_pg, num_simulations)
					writer.writerow([prob_fail, honest_payment_every_seconds, upfront_fee_share, 
						r, r_jam, r < r_jam])


def main():
	run_simulations(num_simulations=5, upfront_fee_share_steps=10)


if __name__ == "__main__":
	main()

#!/usr/bin/env python3

import csv

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
MAX_DELAY = 10
PROB_FAIL = 0.1
# we expect an honest payment every HONEST_PAYMENT_EVERY_SECONDS seconds on average
# in terms of exponential distribution, this is beta (aka scale, aka the inverse of rate lambda)
HONEST_PAYMENT_EVERY_SECONDS = 30

DUST_LIMIT = 1000
JAM_DELAY = MAX_DELAY


def run_simulation(route, payment_generator, simulation_duration):
	elapsed = 0 		# total simulated time elapsed since simulation started
	leftover = 0 		# time to process past payments "carried over" to next payment cycles
	num_skipped = 0 	# number of payments skipped (due to handling other payments)
	num_payments = 0 	# total number of payments received (not necessarily handled)
	while elapsed < simulation_duration:
		payment, time_to_next = payment_generator.next(route)
		num_payments += 1
		elapsed += time_to_next
		#print("leftover, delay, time_to_next, elapsed:", " ".join([str(round(x)) for x in [leftover, payment.delay, time_to_next, elapsed]]))
		if leftover > 0:
			# previous payment is still being handled
			#print("Slot busy, skipping payment")
			num_skipped += 1
			leftover = max(0, leftover - time_to_next)
		else:
			# handle new payment
			#print("Handling payment")
			for node in route:
				node.handle(payment)
			leftover = max(0, payment.delay - time_to_next)
		skip_payment = (payment.delay > time_to_next)
	#print("Skipped", num_skipped, " / ", num_payments, "or", round(num_skipped / num_payments, 2), "of payments.")

def reset_route(route):
	for node in route:
		node.reset()

def run_simulations():
	fp = LinearFeePolicy(BASE_FEE, PROP_FEE_SHARE, 0)
	alice = Node("Alice", fp)
	bob = Node("Bob", fp)
	charlie = Node("Charlie", fp)
	route = [alice, bob, charlie]

	jamming_costs = []
	normal_revenue = []
	upfront_fee_share_range = [x/10 for x in range(11)]

	simulation_duration = 60*60

	for upfront_fee_share in upfront_fee_share_range:
		fp = LinearFeePolicy(BASE_FEE, PROP_FEE_SHARE, upfront_fee_share)
		for node in route:
			node.set_fee_policy(fp)
		pg = HonestPaymentGenerator(route, MIN_AMOUNT, MAX_AMOUNT, MIN_DELAY, MAX_DELAY, PROB_FAIL, HONEST_PAYMENT_EVERY_SECONDS)
		run_simulation(route, pg, simulation_duration)
		r = route[1].revenue
		normal_revenue.append(r)
		reset_route(route)
		jam_pg = JamPaymentGenerator(route, DUST_LIMIT, JAM_DELAY)
		run_simulation(route, jam_pg, simulation_duration)
		r_jam = route[1].revenue
		reset_route(route)
		jamming_costs.append(r_jam)
		

	print("For upfront fee share in: 	", upfront_fee_share_range)
	print("Jamming costs:			", jamming_costs)
	print("Normal revenue:			", normal_revenue)
	cost_of_damage = [(round(100*c/d,2) if d > 0 else None) for c,d in zip(jamming_costs, normal_revenue)]
	print("Cost as % of damage:		", [c for c in cost_of_damage])

	with open("results.csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(upfront_fee_share_range)
		writer.writerow(jamming_costs)

def main():
	run_simulations()

if __name__ == "__main__":
	main()

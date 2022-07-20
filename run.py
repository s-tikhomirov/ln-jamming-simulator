#!/usr/bin/env python3

import argparse
import csv
import statistics
import time
import random
from numpy.random import exponential

from node import Node
from payment import Payment


#### AMOUNTS ####
K = 1000
MIN_AMOUNT = 10 * K
# FIXME: hangs when changing min or max amount, even if same
MAX_AMOUNT = 10 * K
JAM_AMOUNT = 10 * K

#### DELAYS ####
MIN_DELAY = 1
EXPECTED_EXTRA_DELAY = 10
# we expect an honest payment every X seconds on average
# in terms of exponential distribution, this is beta (aka scale, aka the inverse of rate lambda)
HONEST_PAYMENT_EVERY_SECONDS = 30
JAM_DELAY = MIN_DELAY + 2 * EXPECTED_EXTRA_DELAY

#### FEES ####
UPFRONT_BASE = 5
UPFRONT_PROP = 0.02
SUCCESS_BASE = 10
SUCCESS_PROP = 0.05

NUM_SLOTS = 10

# the probability that a payment randomly fails PER HOP
# (a coin is flipped at every routing node)
PROB_NETWORK_FAIL = 0.05

def success_fee_function(a):
	return round(SUCCESS_BASE + SUCCESS_PROP * a)

def upfront_fee_function(a):
	return round(UPFRONT_BASE + UPFRONT_PROP * a)

def honest_time_to_next():
	return exponential(HONEST_PAYMENT_EVERY_SECONDS)

def jamming_time_to_next():
	return JAM_DELAY

def honest_delay():
	return MIN_DELAY + exponential(EXPECTED_EXTRA_DELAY)

def jamming_delay():
	return JAM_DELAY

def honest_amount():
	# Payment amount is uniform between the maximal and minimal values
	# FIXME: find a more suitable distribution.
	# randint() is inclusive
	print("in honest_amount")
	return random.randint(MIN_AMOUNT, MAX_AMOUNT)

def jamming_amount():
	return JAM_AMOUNT

def create_jamming_route():
	# senders can't fail payments
	jammer_sender = Node("JammerSender",
		num_slots=NUM_SLOTS,
		prob_network_fail=0,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=jamming_time_to_next,
		payment_amount_function=jamming_amount,
		payment_delay_function=jamming_delay,
		num_payments_in_batch=NUM_SLOTS)
	# router fails payment with network fail rate
	router = Node("Router",
		num_slots=NUM_SLOTS,
		prob_network_fail=PROB_NETWORK_FAIL,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function)
	# jammer-receiver fails payments deliberately
	jammer_receiver = Node("Jammer_Receiver",
		num_slots=NUM_SLOTS,
		prob_network_fail=0,
		prob_deliberate_fail=1,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function)
	route = [jammer_sender, router, jammer_receiver]
	return route

def create_honest_route():
	honest_sender = Node("Sender",
		num_slots=NUM_SLOTS,
		prob_network_fail=0,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function,
		time_to_next_function=honest_time_to_next,
		payment_amount_function=honest_amount,
		payment_delay_function=honest_delay)
	router = Node("Router",
		num_slots=NUM_SLOTS,
		prob_network_fail=PROB_NETWORK_FAIL,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function)
	honest_receiver = Node("HonestReceiver",
		num_slots=NUM_SLOTS,
		prob_network_fail=PROB_NETWORK_FAIL,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		upfront_fee_function=upfront_fee_function)
	route = [honest_sender, router, honest_receiver]
	return route

def run_simulation(route, simulation_duration):
	elapsed = 0
	sender = route[0]
	while elapsed < simulation_duration:
		payment = sender.create_payment(route)
		print(payment)
		success, time_to_next = sender.route_payment(payment, route)
		elapsed += time_to_next

def average_fee_revenue(route, num_simulations, simulation_duration):
	revenues = []
	for num_simulation in range(num_simulations):
		run_simulation(route, simulation_duration)
		revenues.append(route[1].revenue)
		for node in route:
			node.reset()
	return statistics.mean(revenues)

def run_simulations(num_simulations, simulation_duration):
	honest_route = create_honest_route()
	jamming_route = create_jamming_route()
	timestamp = str(int(time.time()))
	with open("results/" + timestamp + "-revenues" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["prob_network_fail", "honest_payment_every_seconds", 
			"normal_revenue", "jamming_revenue", "jamming_revenue_is_higher"])
		honest_average_revenue = average_fee_revenue(honest_route, num_simulations, simulation_duration)
		# jamming revenue is constant ONLY if PROB_NETWORK_FAIL = 0
		jamming_revenue = average_fee_revenue(jamming_route, num_simulations, simulation_duration)
		break_even_reached = honest_average_revenue < jamming_revenue
		writer.writerow([PROB_NETWORK_FAIL, HONEST_PAYMENT_EVERY_SECONDS,
			round(honest_average_revenue), round(jamming_revenue), break_even_reached])
	print(honest_average_revenue, jamming_revenue)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--num_simulations", default=10, type=int,
		help="The number of simulation runs per parameter combinaiton.")
	parser.add_argument("--simulation_duration", default=60, type=int,
		help="Simulation duration in seconds.")
	args = parser.parse_args()

	run_simulations(args.num_simulations, args.simulation_duration)


if __name__ == "__main__":

	main()

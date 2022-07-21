#!/usr/bin/env python3

import argparse
import csv
import statistics
import time
import random
import math
from numpy.random import exponential, lognormal
import numpy as np

from node import Node
from payment import Payment

K = 1000
M = K * K

#### PAYMENT FLOW PROPERTIES ####

# We assume amounts follow log-normal distribution
# Cf. https://swiftinstitute.org/wp-content/uploads/2012/10/The-Statistics-of-Payments_v15.pdf
# mu is the natural log of the mean amount (we assume 50k sats ~ $10 at $20k per BTC)
# sigma is the measure of how spread out the distribution is
# with sigma = 0.7, maximum values are around 1 million; values above ~300k are rare
AMOUNT_MU = math.log(50 * K)
AMOUNT_SIGMA = 0.7


#### PROTOCOL PROPERTIES ####

# https://github.com/lightning/bolts/blob/master/03-transactions.md#dust-limits
DUST_LIMIT = 354

# max_accepted_htlcs is limited to 483 to ensure that, 
# even if both sides send the maximum number of HTLCs, 
# the commitment_signed message will still be under the maximum message size. 
# It also ensures that a single penalty transaction can spend 
# the entire commitment transaction, as calculated in BOLT #5.
# https://github.com/lightning/bolts/blob/master/02-peer-protocol.md#rationale-7
NUM_SLOTS = 483


#### NETWORK PROPERTIES ####

# average payment resolution time was 3-4 seconds in 2020:
# https://arxiv.org/abs/2004.00333 (Section 4.4)
MIN_DELAY = 1
EXPECTED_EXTRA_DELAY = 3

# in terms of exponential distribution, this is beta
# (aka scale, aka the inverse of rate lambda)
HONEST_PAYMENT_EVERY_SECONDS = 10

# the probability that a payment randomly fails PER HOP
# (a coin is flipped at every routing node)
# however, if we set it only for Router but not HonestReceiver,
# this probability would reflect the failure probability of the whole route
# TODO: make the failure probability depend on the amount?
PROB_NETWORK_FAIL = 0.05


#### JAMMING PARAMETERS ####

# nodes may set stricter dust limit
JAM_AMOUNT = DUST_LIMIT

JAM_DELAY = MIN_DELAY + 2 * EXPECTED_EXTRA_DELAY


#### FEES ####

# LN implementations use the following default values for base / rate:
# LND: 1 sat / 1 per million
# https://docs.lightning.engineering/lightning-network-tools/lnd/channel-fees
# https://github.com/lightningnetwork/lnd/blob/master/sample-lnd.conf
# Core Lightning: 1 sat / 10 per million
# https://lightning.readthedocs.io/lightningd-config.5.html#lightning-node-customization-options
# Eclair: ?
# LDK: ?
# Let's use _success-case_ fees similar to currently used ones,
# and vary the _upfront-case_ fees across experiments

SUCCESS_BASE = 1
SUCCESS_RATE = 5 / M


def generic_fee_function(a, base, rate):
	return base + rate * a

def success_fee_function(a):
	# we don't round to satoshis to avoid rounding to zero
	return generic_fee_function(a, SUCCESS_BASE, SUCCESS_RATE)

def honest_time_to_next():
	return exponential(HONEST_PAYMENT_EVERY_SECONDS)

def jamming_time_to_next():
	return JAM_DELAY

def honest_delay():
	return MIN_DELAY + exponential(EXPECTED_EXTRA_DELAY)

def jamming_delay():
	return JAM_DELAY

def honest_amount():
	return lognormal(mean=AMOUNT_MU, sigma=AMOUNT_SIGMA)

def jamming_amount():
	return JAM_AMOUNT

def create_jamming_route():
	# senders can't fail payments
	jammer_sender = Node("JammerSender",
		num_slots=NUM_SLOTS,
		prob_network_fail=0,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		time_to_next_function=jamming_time_to_next,
		payment_amount_function=jamming_amount,
		payment_delay_function=jamming_delay,
		num_payments_in_batch=NUM_SLOTS)
	# router fails payment with network fail rate
	router = Node("Router",
		num_slots=NUM_SLOTS,
		prob_network_fail=PROB_NETWORK_FAIL,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function)
	# jammer-receiver fails payments deliberately
	jammer_receiver = Node("Jammer_Receiver",
		num_slots=NUM_SLOTS,
		prob_network_fail=0,
		prob_deliberate_fail=1,
		success_fee_function=success_fee_function)
	route = [jammer_sender, router, jammer_receiver]
	return route

def create_honest_route():
	honest_sender = Node("Sender",
		num_slots=NUM_SLOTS,
		prob_network_fail=0,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function,
		time_to_next_function=honest_time_to_next,
		payment_amount_function=honest_amount,
		payment_delay_function=honest_delay)
	router = Node("Router",
		num_slots=NUM_SLOTS,
		prob_network_fail=PROB_NETWORK_FAIL,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function)
	honest_receiver = Node("HonestReceiver",
		num_slots=NUM_SLOTS,
		prob_network_fail=PROB_NETWORK_FAIL,
		prob_deliberate_fail=0,
		success_fee_function=success_fee_function)
	route = [honest_sender, router, honest_receiver]
	return route

def run_simulation(route, simulation_duration):
	elapsed = 0
	sender = route[0]
	while elapsed < simulation_duration:
		payment = sender.create_payment(route)
		success, time_to_next = sender.route_payment(payment, route)
		elapsed += time_to_next

def average_fee_revenue(route, num_simulations, simulation_duration):
	revenues = []
	for num_simulation in range(num_simulations):
		run_simulation(route, simulation_duration)
		revenues.append(route[1].revenue)
		for node in route:
			node.reset()
	return round(statistics.mean(revenues))

def run_simulations(num_simulations, simulation_duration):
	honest_route = create_honest_route()
	jamming_route = create_jamming_route()
	timestamp = str(int(time.time()))
	with open("results/" + timestamp + "-revenues" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["num_simulations: " + str(num_simulations)])
		writer.writerow(["simulation_duration: " + str(simulation_duration)])
		writer.writerow(["success_base: " + str(SUCCESS_BASE)])
		writer.writerow(["success_rate: " + str(SUCCESS_RATE)])
		writer.writerow("")
		writer.writerow(["upfront_base_coeff", "upfront_rate_coeff", 
			"upfront_base", "upfront_rate",
			"normal_revenue", "jamming_revenue", "jamming_revenue_is_higher"])
		num_parameter_sets = len(UPFRONT_BASE_COEFF_RANGE) * len(UPFRONT_RATE_COEFF_RANGE)
		i = 1
		for upfront_base_coeff in UPFRONT_BASE_COEFF_RANGE:
			for upfront_rate_coeff in UPFRONT_RATE_COEFF_RANGE:
				print("\nSimulation", i ,"of", num_parameter_sets)
				i += 1
				print("upfront_base_coeff, upfront_rate_coeff:		",
					upfront_base_coeff, upfront_rate_coeff)
				upfront_base = upfront_base_coeff * SUCCESS_BASE
				upfront_rate = upfront_rate_coeff * SUCCESS_RATE
				def upfront_fee_function(a):
					return generic_fee_function(a, base=upfront_base, rate=upfront_rate)
				for node in jamming_route + honest_route:
					node.upfront_fee_function = upfront_fee_function
				# jamming revenue is constant ONLY if PROB_NETWORK_FAIL = 0
				# that's why we must average across experiments both for jamming and honest cases
				jamming_revenue = average_fee_revenue(jamming_route, num_simulations, simulation_duration)
				honest_average_revenue = average_fee_revenue(honest_route, num_simulations, simulation_duration)
				break_even_reached = honest_average_revenue < jamming_revenue
				writer.writerow([
					upfront_base_coeff, 
					upfront_rate_coeff,
					np.format_float_positional(upfront_base),
					np.format_float_positional(upfront_rate),
					round(honest_average_revenue), 
					round(jamming_revenue),
					break_even_reached])
				print("honest_average_revenue, jamming_revenue:	", 
					honest_average_revenue, jamming_revenue)


COMMON_RANGE = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]

# upfront base fee it this many times higher than success-case base fee
UPFRONT_BASE_COEFF_RANGE = COMMON_RANGE
# upfront fee rate is this many times higher than success-case fee rate
UPFRONT_RATE_COEFF_RANGE = COMMON_RANGE

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

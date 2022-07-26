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

# Amounts follow log-normal distribution
# Cf. https://swiftinstitute.org/wp-content/uploads/2012/10/The-Statistics-of-Payments_v15.pdf
# mu is the natural log of the mean amount (we assume 50k sats ~ $10 at $20k per BTC)
# sigma is the measure of how spread out the distribution is
# with sigma = 0.7, maximum values are around 1 million; values above ~300k are rare
AMOUNT_MU = math.log(50 * K)
AMOUNT_SIGMA = 0.7


#### PROTOCOL PROPERTIES ####

# all payment amounts (on every layer) must be higher than dust limie
# (otherwise HTLCs are trimmed)
# jams are a just bit higher than dust limit
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

# the probability that a payment fails at a hop
# because the _next_ channel can't handle it (e.g., low balance)
PROB_NEXT_CHANNEL_LOW_BALANCE = 0


#### JAMMING PARAMETERS ####

# nodes may set stricter dust limits
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
	jammer_sender = Node("JammerSender",
		num_slots=NUM_SLOTS,
		time_to_next_function=jamming_time_to_next,
		payment_amount_function=jamming_amount,
		payment_delay_function=jamming_delay,
		num_payments_in_batch=NUM_SLOTS,
		subtract_upfront_fee_from_last_hop_amount=False)
	router = Node("Router",
		num_slots=NUM_SLOTS,
		prob_next_channel_low_balance=PROB_NEXT_CHANNEL_LOW_BALANCE,
		success_fee_function=success_fee_function)
	# jammer-receiver always deliberately fails payments
	jammer_receiver = Node("Jammer_Receiver",
		num_slots=NUM_SLOTS,
		prob_deliberately_fail=1,
		success_fee_function=success_fee_function)
	route = [jammer_sender, router, jammer_receiver]
	return route

def create_honest_route():
	honest_sender = Node("Sender",
		num_slots=NUM_SLOTS,
		time_to_next_function=honest_time_to_next,
		payment_amount_function=honest_amount,
		payment_delay_function=honest_delay)
	router = Node("Router",
		num_slots=NUM_SLOTS,
		prob_next_channel_low_balance=PROB_NEXT_CHANNEL_LOW_BALANCE,
		success_fee_function=success_fee_function)
	honest_receiver = Node("HonestReceiver",
		num_slots=NUM_SLOTS,
		success_fee_function=success_fee_function)
	route = [honest_sender, router, honest_receiver]
	return route

def run_simulation(route, simulation_duration):
	elapsed = 0
	sender = route[0]
	num_payments, num_failed = 0, 0
	while elapsed < simulation_duration:
		payment = sender.create_payment(route)
		success, time_to_next = sender.route_payment(payment, route)
		num_payments += 1
		if not success:
			num_failed += 1
		elapsed += time_to_next
	return num_payments, num_failed

def average_result_values(route, num_simulations, simulation_duration):
	sender_revenues, router_revenues, num_payments_values, num_failed_values = [], [], [], []
	for num_simulation in range(num_simulations):
		num_payments, num_failed = run_simulation(route, simulation_duration)
		sender_revenues.append(route[0].revenue)
		router_revenues.append(route[1].revenue)
		num_payments_values.append(num_payments)
		num_failed_values.append(num_failed)
		for node in route:
			node.reset()
	return (
		statistics.mean(sender_revenues),
		statistics.mean(router_revenues),
		statistics.mean(num_payments_values),
		statistics.mean(num_failed_values)
		)


def run_simulations(num_simulations, simulation_duration):
	honest_route = create_honest_route()
	jamming_route = create_jamming_route()
	timestamp = str(int(time.time()))
	with open("results/" + timestamp + "-revenues" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["num_simulations", str(num_simulations)])
		writer.writerow(["simulation_duration", str(simulation_duration)])
		writer.writerow(["success_base", str(SUCCESS_BASE)])
		writer.writerow(["success_rate", str(SUCCESS_RATE)])
		writer.writerow(["HONEST_PAYMENT_EVERY_SECONDS", str(HONEST_PAYMENT_EVERY_SECONDS)])
		writer.writerow(["JAM_DELAY", str(JAM_DELAY)])
		writer.writerow(["JAM_AMOUNT", str(JAM_AMOUNT)])
		writer.writerow(["NUM_SLOTS", str(NUM_SLOTS)])
		writer.writerow(["PROB_NEXT_CHANNEL_LOW_BALANCE", PROB_NEXT_CHANNEL_LOW_BALANCE])
		writer.writerow("")
		writer.writerow([
			"upfront_base_coeff", "upfront_rate_coeff",
			"upfront_base", "upfront_rate",
			"num_payments_honest", "num_failed_honest", "share_failed",
			"num_jams",
			"sender_revenue_honest", "sender_revenue_jamming",
			"router_revenue_honest", "router_revenue_jamming",
			"router_revenue_jamming_is_higher_than_honest"])
		num_parameter_sets = len(UPFRONT_BASE_COEFF_RANGE) * len(UPFRONT_RATE_COEFF_RANGE)
		i = 1
		for upfront_base_coeff in UPFRONT_BASE_COEFF_RANGE:
			for upfront_rate_coeff in UPFRONT_RATE_COEFF_RANGE:
				print("\nParameter combination", i ,"of", num_parameter_sets)
				i += 1
				print("upfront_base_coeff, upfront_rate_coeff:		",
					upfront_base_coeff, upfront_rate_coeff)
				upfront_base = upfront_base_coeff * SUCCESS_BASE
				upfront_rate = upfront_rate_coeff * SUCCESS_RATE
				def upfront_fee_function(a):
					return generic_fee_function(a, base=upfront_base, rate=upfront_rate)
				for node in jamming_route + honest_route:
					node.upfront_fee_function = upfront_fee_function
				# jamming revenue is constant ONLY if PROB_NEXT_CHANNEL_LOW_BALANCE = 0
				# that's why we must average across experiments both for jamming and honest cases
				random.seed(0)
				np.random.seed(0)
				sender_revenue_j, router_revenue_j, num_p_j, num_f_j = average_result_values(jamming_route, num_simulations, simulation_duration)
				assert(num_p_j == num_f_j)
				sender_revenue_h, router_revenue_h, num_p_h, num_f_h = average_result_values(honest_route, num_simulations, simulation_duration)
				share_failed_h = num_f_h/num_p_h
				print("\nOn average per simulation (honest):", 
					num_p_h, "payments,",
					num_f_h, "(", round(num_f_h/num_p_h,2), ") of them failed.")
				print("Per-hop low balance probabiliy is", PROB_NEXT_CHANNEL_LOW_BALANCE)
				print("On average per simulation (jamming):", 
					num_p_j, "payments,",
					num_f_j, "of them failed.")
				print("Sender's revenue (honest, jamming):	", sender_revenue_h, sender_revenue_j)
				print("Router's revenue (honest, jamming):	", router_revenue_h, router_revenue_j)
				router_revenue_jamming_is_higher_than_honest = router_revenue_j > router_revenue_h
				writer.writerow([
					upfront_base_coeff, 
					upfront_rate_coeff,
					np.format_float_positional(upfront_base),
					# due to rounding, upfront_rate may take the form like
					# 0.0000005000000000000001
					# let's round it to 12 decimal points
					np.format_float_positional(round(upfront_rate,12)),
					num_p_h,
					num_f_h,
					share_failed_h,
					num_p_j,
					sender_revenue_h,
					sender_revenue_j,
					router_revenue_h,
					router_revenue_j,
					router_revenue_jamming_is_higher_than_honest
					])


#COMMON_RANGE = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
COMMON_RANGE = [0.01, 0.1, 1]

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

#!/usr/bin/env python3

import argparse
import csv
import numpy as np
import random
import statistics
import time

from numpy.random import exponential, lognormal

from node import Node
from payment import Payment

from params import PaymentFlowParams, FeeParams, JammingParams


def generic_fee_function(a, base, rate):
	return base + rate * a

def success_fee_function(a):
	return generic_fee_function(a, FeeParams["SUCCESS_BASE"], FeeParams["SUCCESS_RATE"])

def honest_time_to_next():
	return exponential(PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"])
def honest_delay():
	return PaymentFlowParams["MIN_DELAY"] + exponential(PaymentFlowParams["EXPECTED_EXTRA_DELAY"])
def honest_amount():
	return lognormal(mean=PaymentFlowParams["AMOUNT_MU"], sigma=PaymentFlowParams["AMOUNT_SIGMA"])

def jamming_time_to_next():
	return JammingParams["JAM_DELAY"]
def jamming_delay():
	return JammingParams["JAM_DELAY"]
def jamming_amount():
	return JammingParams["JAM_AMOUNT"]

jammer_sender = Node("JammerSender",
	time_to_next_function=jamming_time_to_next,
	payment_amount_function=jamming_amount,
	payment_delay_function=jamming_delay,
	num_payments_in_batch=JammingParams["JAM_BATCH_SIZE"],
	subtract_upfront_fee_from_last_hop_amount=False)
jammer_receiver = Node("Jammer_Receiver",
	prob_deliberately_fail=1,
	success_fee_function=success_fee_function)
honest_sender = Node("Sender",
	time_to_next_function=honest_time_to_next,
	payment_amount_function=honest_amount,
	payment_delay_function=honest_delay)
router = Node("Router",
	success_fee_function=success_fee_function)
honest_receiver = Node("HonestReceiver",
	success_fee_function=success_fee_function)

honest_route = [honest_sender, router, honest_receiver]
jamming_route = [jammer_sender, router, jammer_receiver]


def run_simulation(route, simulation_duration):
	sender, elapsed, num_payments, num_failed = route[0], 0, 0, 0
	while elapsed < simulation_duration:
		payment = sender.create_payment(route)
		success, time_to_next = sender.route_payment(payment, route)
		num_payments += 1
		if not success:
			num_failed += 1
		elapsed += time_to_next
	return num_payments, num_failed

def average_result_values(route, num_simulations, simulation_duration):
	sender_revenues, router_revenues, receiver_revenues, num_payments_values, num_failed_values = [], [], [], [], []
	for num_simulation in range(num_simulations):
		print("Simulation", num_simulation + 1, "of", num_simulations)
		num_payments, num_failed = run_simulation(route, simulation_duration)
		sender_revenues.append(route[0].revenue)
		router_revenues.append(route[1].revenue)
		receiver_revenues.append(route[2].revenue)
		num_payments_values.append(num_payments)
		num_failed_values.append(num_failed)
		for node in route:
			node.reset()
	return (
		statistics.mean(sender_revenues),
		statistics.mean(router_revenues),
		statistics.mean(receiver_revenues),
		statistics.mean(num_payments_values),
		statistics.mean(num_failed_values)
		)

def run_simulations(num_simulations, simulation_duration):
	timestamp = str(int(time.time()))
	with open("results/" + timestamp + "-revenues" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["num_simulations", str(num_simulations)])
		writer.writerow(["simulation_duration", str(simulation_duration)])
		writer.writerow(["success_base", str(FeeParams["SUCCESS_BASE"])])
		writer.writerow(["success_rate", str(FeeParams["SUCCESS_RATE"])])
		writer.writerow(["HONEST_PAYMENT_EVERY_SECONDS", str(PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"])])
		writer.writerow(["JAM_DELAY", str(JammingParams["JAM_DELAY"])])
		writer.writerow(["JAM_AMOUNT", str(JammingParams["JAM_AMOUNT"])])
		writer.writerow("")
		writer.writerow([
			"upfront_base_coeff", "upfront_rate_coeff",
			"upfront_base", "upfront_rate",
			"num_payments_honest", "num_failed_honest", "share_failed",
			"num_jams",
			"h_sender_revenue", "j_sender_revenue",
			"h_router_revenue", "j_router_revenue",
			"h_receiver_revenue", "j_receiver_revenue",
			"j_attack_cost"])
		num_parameter_sets = len(UPFRONT_BASE_COEFF_RANGE) * len(UPFRONT_RATE_COEFF_RANGE)
		i = 1
		for upfront_base_coeff in UPFRONT_BASE_COEFF_RANGE:
			for upfront_rate_coeff in UPFRONT_RATE_COEFF_RANGE:
				print("\nParameter combination", i ,"of", num_parameter_sets)
				i += 1
				upfront_base = upfront_base_coeff * FeeParams["SUCCESS_BASE"]
				upfront_rate = upfront_rate_coeff * FeeParams["SUCCESS_RATE"]
				def upfront_fee_function(a):
					return generic_fee_function(a, base=upfront_base, rate=upfront_rate)
				for node in jamming_route + honest_route:
					node.upfront_fee_function = upfront_fee_function
				# jamming revenue is constant ONLY if PROB_NEXT_CHANNEL_LOW_BALANCE = 0
				# that's why we must average across experiments both for jamming and honest cases
				sender_revenue_j, router_revenue_j, receiver_revenue_j, num_p_j, num_f_j = average_result_values(jamming_route, num_simulations, simulation_duration)
				assert(num_p_j == num_f_j)
				attack_cost_j = sender_revenue_j + receiver_revenue_j
				sender_revenue_h, router_revenue_h, receiver_revenue_h, num_p_h, num_f_h = average_result_values(honest_route, num_simulations, simulation_duration)
				share_failed_h = num_f_h/num_p_h
				print("\nOn average per simulation (honest):", 
					num_p_h, "payments,",
					num_f_h, "(", round(num_f_h/num_p_h,2), ") of them failed.")
				print("On average per simulation (jamming):", 
					num_p_j, "payments,",
					num_f_j, "of them failed.")
				print("Sender's revenue (honest, jamming):	", sender_revenue_h, sender_revenue_j)
				print("Router's revenue (honest, jamming):	", router_revenue_h, router_revenue_j)
				print("Receiver's revenue (honest, jamming):	", receiver_revenue_h, receiver_revenue_j)
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
					receiver_revenue_h,
					receiver_revenue_j,
					attack_cost_j
					])


COMMON_RANGE = [0.01, 0.1, 1, 10, 100]

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
	parser.add_argument("--seed", type=int,
		help="Seed for randomness initialization.")
	args = parser.parse_args()

	if args.seed is not None:
		print("Initializing randomness seed:", args.seed)
		random.seed(args.seed)
		np.random.seed(args.seed)

	start_time = time.time()
	run_simulations(args.num_simulations, args.simulation_duration)
	end_time = time.time()
	running_time = end_time - start_time

	print("\nRunning time (min):", round(running_time / 60, 1))


if __name__ == "__main__":

	main()

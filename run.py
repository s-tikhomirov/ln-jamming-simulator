#!/usr/bin/env python3

import argparse
import csv
import numpy as np
import random
import statistics
import time
from math import ceil

from numpy.random import exponential, lognormal

from node import Node
from payment import Payment

from params import PaymentFlowParams, FeeParams, JammingParams, ProtocolParams


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
	prob_next_channel_low_balance=0,
	time_to_next_function=jamming_time_to_next,
	payment_amount_function=jamming_amount,
	payment_delay_function=jamming_delay,
	num_payments_in_batch=JammingParams["JAM_BATCH_SIZE"],
	subtract_upfront_fee_from_last_hop_amount=False)

jammer_receiver = Node("Jammer_Receiver",
	prob_deliberately_fail=1,
	success_fee_function=success_fee_function)

honest_sender = Node("Sender",
	prob_next_channel_low_balance=0,
	time_to_next_function=honest_time_to_next,
	payment_amount_function=honest_amount,
	payment_delay_function=honest_delay)

router = Node("Router",
	success_fee_function=success_fee_function)

honest_receiver = Node("HonestReceiver",
	success_fee_function=success_fee_function)

honest_route = [honest_sender, router, honest_receiver]
jamming_route = [jammer_sender, router, jammer_receiver]

def run_simulation(route, simulation_duration, no_balance_failures=False):
	sender, receiver, elapsed, num_payments, num_failed = route[0], route[-1], 0, 0, 0
	if no_balance_failures:
		num_batches = ceil(simulation_duration / JammingParams["JAM_DELAY"])
		jams_in_batch = ProtocolParams["NUM_SLOTS"]
		num_payments = num_batches * jams_in_batch
		num_failed = num_payments
		p = sender.create_payment(route)
		sender.upfront_revenue = - num_payments * p.upfront_fee
		for node in route[1:-1]:
			node.upfront_revenue = num_payments * (p.upfront_fee - p.downstream_payment.upfront_fee)
			p = p.downstream_payment
		receiver.upfront_revenue = num_payments * p.upfront_fee
		for node in route:
			node.success_revenue = 0
			node.revenue = node.upfront_revenue + node.success_revenue
	else:
		while elapsed < simulation_duration:
			payment = sender.create_payment(route)
			success, time_to_next = sender.route_payment(payment, route)
			num_payments += 1
			if not success:
				num_failed += 1
			elapsed += time_to_next
	return num_payments, num_failed

def average_result_values(route, num_simulations, simulation_duration, no_balance_failures=False):
	sender_revenues, router_revenues, receiver_revenues = [], [], []
	sender_upfront_revenue_shares, router_upfront_revenue_shares, receiver_upfront_revenue_shares = [], [], []
	num_payments_values, num_failed_values = [], []
	# if probability of failure is 0, we run just one simulation for jamming
	# it doesn't make sense to repeat because the results are deterministic
	if no_balance_failures:
		print("With zero failure probability, jamming simulations are done analytically.")
	effective_num_simulations = num_simulations if no_balance_failures else num_simulations
	for num_simulation in range(effective_num_simulations):
		print("Simulation", num_simulation + 1, "of", effective_num_simulations)
		num_payments, num_failed = run_simulation(route, simulation_duration, no_balance_failures)
		sender_revenues.append(route[0].revenue)
		router_revenues.append(route[1].revenue)
		receiver_revenues.append(route[2].revenue)
		sender_upfront_revenue_share = route[0].upfront_revenue / route[0].revenue if route[0].revenue != 0 else 0
		router_upfront_revenue_share = route[1].upfront_revenue / route[1].revenue if route[1].revenue != 0 else 0
		receiver_upfront_revenue_share = route[2].upfront_revenue / route[2].revenue if route[2].revenue != 0 else 0
		# generally speaking, upfront revenue can be positive while success revenue is negative, or vice versa
		# in that case, upfront fee "share" would be negative - for now, just assert that it's not the case
		assert(sender_upfront_revenue_share >= 0 and router_upfront_revenue_share >= 0 and receiver_upfront_revenue_share >= 0)
		sender_upfront_revenue_shares.append(sender_upfront_revenue_share)
		router_upfront_revenue_shares.append(router_upfront_revenue_share)
		receiver_upfront_revenue_shares.append(receiver_upfront_revenue_share)
		num_payments_values.append(num_payments)
		num_failed_values.append(num_failed)
		for node in route:
			node.reset()
	return (
		statistics.mean(sender_revenues),
		statistics.mean(router_revenues),
		statistics.mean(receiver_revenues),
		statistics.mean(sender_upfront_revenue_shares),
		statistics.mean(router_upfront_revenue_shares),
		statistics.mean(receiver_upfront_revenue_shares),
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
		writer.writerow(["PROB_NEXT_CHANNEL_LOW_BALANCE", str(PaymentFlowParams["PROB_NEXT_CHANNEL_LOW_BALANCE"])])
		writer.writerow(["JAM_DELAY", str(JammingParams["JAM_DELAY"])])
		writer.writerow(["JAM_AMOUNT", str(JammingParams["JAM_AMOUNT"])])
		writer.writerow("")
		writer.writerow([
			"upfront_base_coeff", "upfront_rate_coeff",
			"upfront_base", "upfront_rate",
			"num_payments_honest", "num_failed_honest", "share_failed",
			"num_jams",
			"h_snd_revenue",
			"h_snd_upfront_share",
			"j_snd_revenue",
			"j_snd_upfront_share",
			"h_rtr_revenue",
			"h_rtr_upfront_share",
			"j_rtr_revenue",
			"j_rtr_upfront_share",
			"h_rcv_revenue",
			"h_rcv_upfront_share",
			"j_rcv_revenue",
			"j_rcv_upfront_share",
			"j_attack_cost"])
		num_parameter_sets = len(UPFRONT_BASE_COEFF_RANGE) * len(UPFRONT_RATE_COEFF_RANGE)
		i = 1
		print("Upfront base coeff in", UPFRONT_BASE_COEFF_RANGE)
		print("Upfront rate coeff in", UPFRONT_RATE_COEFF_RANGE)
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
				no_failures = PaymentFlowParams["PROB_NEXT_CHANNEL_LOW_BALANCE"] == 0
				print("Simulating jamming scenario")
				(
					sender_revenue_j, router_revenue_j, receiver_revenue_j, 
					sender_upfront_revenue_shares_j, router_upfront_revenue_shares_j, receiver_upfront_revenue_shares_j,
					num_p_j, num_f_j
					) = average_result_values(jamming_route, num_simulations, simulation_duration, no_failures)
				assert(num_p_j == num_f_j)
				attack_cost_j = sender_revenue_j + receiver_revenue_j
				print("Simulating honest scenario")
				(
					sender_revenue_h, router_revenue_h, receiver_revenue_h, 
					sender_upfront_revenue_shares_h, router_upfront_revenue_shares_h, receiver_upfront_revenue_shares_h,
					num_p_h, num_f_h
					) = average_result_values(honest_route, num_simulations, simulation_duration)
				share_failed_h = num_f_h/num_p_h
				print("\nOn average per simulation (honest):", 
					num_p_h, "payments,",
					num_f_h, "(", round(num_f_h/num_p_h,2), ") of them failed.")
				print("On average per simulation (jamming):", 
					num_p_j, "payments,",
					num_f_j, "of them failed.")
				#print("Sender's revenue (honest, jamming):	", sender_revenue_h, sender_revenue_j)
				#print("Router's revenue (honest, jamming):	", router_revenue_h, router_revenue_j)
				#print("Receiver's revenue (honest, jamming):	", receiver_revenue_h, receiver_revenue_j)
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
					sender_upfront_revenue_shares_h,
					sender_revenue_j,
					sender_upfront_revenue_shares_j,
					router_revenue_h,
					router_upfront_revenue_shares_h,
					router_revenue_j,
					router_upfront_revenue_shares_j,
					receiver_revenue_h,
					receiver_upfront_revenue_shares_h,
					receiver_revenue_j,
					receiver_upfront_revenue_shares_j,
					attack_cost_j
					])


COMMON_RANGE = [0, 0.001, 0.002, 0.003]

# upfront base fee / fee rate it this many times higher than success-case counterparts
UPFRONT_BASE_COEFF_RANGE = COMMON_RANGE
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

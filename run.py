#! /usr/bin/python3

from node import Node
from payment import Payment, PaymentGenerator, JamPaymentGenerator
from fee import LinearFeePolicy

# Parameters for fee calculation:
BASE_FEE 			= 500
PROP_FEE_SHARE 		= 0.01
#UPFRONT_FEE_SHARE 	= 0

# Parameters for payment generation:
K = 1000
MIN_AMOUNT = 1 * K
MAX_AMOUNT = 100 * K
MIN_DELAY = 1
MAX_DELAY = 10
PROB_FAIL = 0.1

DUST_LIMIT = 1000
JAM_DELAY = MAX_DELAY


def run_simulation(route, payment_generator, simulation_duration):
	elapsed = 0
	while elapsed < simulation_duration:
		payment = payment_generator.next(route)
		elapsed += payment.delay
		for node in route:
			node.handle(payment)

def reset_route(route):
	for node in route:
		node.reset()

def main():
	fp = LinearFeePolicy(BASE_FEE, PROP_FEE_SHARE, 0)
	alice = Node("Alice", fp)
	bob = Node("Bob", fp)
	charlie = Node("Charlie", fp)
	route = [alice, bob, charlie]

	jamming_costs = []
	jamming_damage = []
	upfront_fee_share_range = [x/10 for x in range(11)]

	simulation_duration = 60*60

	for upfront_fee_share in upfront_fee_share_range:
		fp = LinearFeePolicy(BASE_FEE, PROP_FEE_SHARE, upfront_fee_share)
		for node in route:
			node.set_fee_policy(fp)
		pg = PaymentGenerator(route, MIN_AMOUNT, MAX_AMOUNT, MIN_DELAY, MAX_DELAY, PROB_FAIL)
		jam_pg = JamPaymentGenerator(route, DUST_LIMIT, JAM_DELAY)
		run_simulation(route, pg, simulation_duration)
		r = route[1].revenue
		reset_route(route)
		run_simulation(route, jam_pg, simulation_duration)
		r_jam = route[1].revenue
		reset_route(route)
		jamming_costs.append(r_jam)
		jamming_damage.append(r - r_jam)

	print("For upfront fee share in: 	", upfront_fee_share_range)
	print("Jamming costs:			", jamming_costs)
	print("Damage (foregone revenue):	", jamming_damage)
	cost_of_damage = [(round(100*c/d,2) if d > 0 else None) for c,d in zip(jamming_costs, jamming_damage)]
	print("Cost as % of damage:		", [c for c in cost_of_damage])


if __name__ == "__main__":
	main()

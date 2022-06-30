#! /usr/bin/python3

import random

class Node:

	def __init__(self, name):
		self.name = name
		self.reset()
		
	def reset(self):
		self.revenue, self.amount_forwarded, self.total_payments, self.failed_payments = 0, 0, 0, 0

	def handle_payment(self, payment):
		#print("handling payment:", payment)
		#print("taking upfront fee ", payment.upfront_fee)
		self.total_payments += 1
		self.revenue += payment.upfront_fee
		if payment.success:
			#print("taking success fee ", payment.success_fee)
			self.amount_forwarded += payment.amount
			self.revenue += payment.success_fee
		else:
			self.failed_payments += 1
	
	def __str__(self):
		s = ""
		s = "Node " + self.name
		s += "\nPayments handled: 	" + str(self.total_payments)
		s += "\n	of them failed: " + str(self.failed_payments)
		if self.total_payments > 0:
			s += "\nShare of failed:	" + str(round(self.failed_payments / self.total_payments, 4))
		s += "\n\nValue forwarded: 	" + str(self.amount_forwarded)
		s += "\nRevenue: 		" + str(self.revenue)
		if self.amount_forwarded > 0:
			s += "\nRevenue to value:	" + str(round(self.revenue / self.amount_forwarded, 4))
		s += "\n  per payment handled:	" + str(round(self.revenue / self.total_payments))
		return s


class Payment:
	'''
		A payment has amount + fee. Fee depends on the amount.
		Fee consists of two parts: base and proportional.
		Fee amount is THEN divided into upfront share and the rest (success-case).
	'''
	def __init__(self, amount, delay, success, fee_policy):
		self.amount = amount
		self.delay = delay
		self.success = success
		self.upfront_fee, self.success_fee = fee_policy.calculate_fees(amount)

	def __str__(self):
		total_fee = self.upfront_fee + self.success_fee
		s = "Payment with amount " + str(self.amount)
		s += "\n  Total fee:	" + str(total_fee) \
		+ "\n    in %:	" + str(round(100 * total_fee / self.amount))
		s += "\n  upfront fee:	" + str(self.upfront_fee)
		s += "\n  success_fee:	" + str(self.success_fee)
		return s


class PaymentGenerator:
	
	def __init__(self, min_amount, max_amount, min_delay, max_delay, prob_fail, fee_policy):
		# Check that total fee is lower than amount, even for min_amount
		try:
			min_total_fee = fee_policy.calculate_total_fee(min_amount)
		except Exception as e:
			print("Checking fee for minimal amount:")
			print(e)
			print("Fee calculation is incompatible with payment generator parameters.")
			print("Decrease base fee or increase minimal amount.")
			exit()
		self.min_amount = min_amount
		self.max_amount = max_amount
		self.min_delay = min_delay
		self.max_delay = max_delay
		self.prob_fail = prob_fail
		self.fee_policy = fee_policy

	def next(self):
		# All randomness should happen here.
		amount 		= random.randint(self.min_amount, self.max_amount)
		delay 		= random.randint(self.min_delay, self.max_delay)
		success 	= random.random() > self.prob_fail
		return Payment(amount, delay, success, self.fee_policy)


class JamPaymentGenerator(PaymentGenerator):

	def __init__(self, jam_amount, jam_delay, fee_policy):
		PaymentGenerator.__init__(self, min_amount = jam_amount, max_amount = jam_amount,
			min_delay = jam_delay, max_delay = jam_delay, prob_fail = 1, fee_policy = fee_policy)

	def next(self):
		return Payment(self.min_amount, self.max_delay, success=False, fee_policy=self.fee_policy)


class FeePolicy:

	def __init__(self):
		pass

	def calculate_fees(self):
		raise NotImplementedError


class LinearFeePolicy(FeePolicy):

	def __init__(self, base_fee, prop_fee_share, upfront_fee_share):
		self.base_fee = base_fee
		self.prop_fee_share = prop_fee_share
		self.upfront_fee_share = upfront_fee_share
		FeePolicy.__init__(self)

	def calculate_total_fee(self, amount):
		total_fee = round(self.base_fee + self.prop_fee_share * amount)
		if total_fee > amount:
			raise Exception("Total fee is " + str(total_fee) + " > " + str(amount))
		return total_fee

	def calculate_fees(self, amount):
		total_fee = self.calculate_total_fee(amount)
		upfront_fee = round(total_fee * self.upfront_fee_share)
		success_fee = total_fee - upfront_fee
		return upfront_fee, success_fee


def total_revenue_simulated(node, payment_generator, simulation_duration):
	#print("\n\n--------\n\n")
	#print("Simulating a single node...")
	elapsed = 0
	while elapsed < simulation_duration:
		payment = payment_generator.next()
		elapsed += payment.delay
		node.handle_payment(payment)
	#print(node)
	r = node.revenue
	node.reset()
	return r


# Parameters for fee calculation:
BASE_FEE 			= 500
PROP_FEE_SHARE 		= 0.05
UPFRONT_FEE_SHARE 	= 0.5

# Parameters for payment generation:
MIN_AMOUNT = 1*1000
MAX_AMOUNT = 100*1000
MIN_DELAY = 1
MAX_DELAY = 10
PROB_FAIL = 0.2

DUST_LIMIT = 1000
JAM_DELAY = MAX_DELAY


def main():

	alice = Node(name="Alice")
	experiment_duration = 60*60*24

	jamming_costs = []
	jamming_damage = []
	upfront_fee_share_range = [0, 0.3, 0.6, 0.9]

	for upfront_fee_share in upfront_fee_share_range:
		fc = LinearFeePolicy(BASE_FEE, PROP_FEE_SHARE, upfront_fee_share)
		pg = PaymentGenerator(MIN_AMOUNT, MAX_AMOUNT, MIN_DELAY, MAX_DELAY, PROB_FAIL, fc)
		jam_pg = JamPaymentGenerator(DUST_LIMIT, JAM_DELAY, fc)
		r = total_revenue_simulated(alice, pg, experiment_duration)
		r_jam = total_revenue_simulated(alice, jam_pg, experiment_duration)
		jamming_costs.append(r_jam)
		jamming_damage.append(r - r_jam)

	print("For upfront fee share in: 	", upfront_fee_share_range)
	print("Jamming costs:			", jamming_costs)
	print("Damage (foregone revenue):	", jamming_damage)
	cost_of_damage = [(round(100*c/d,2) if d > 0 else None) for c,d in zip(jamming_costs, jamming_damage)]
	print("Cost as % of damage:		", [c for c in cost_of_damage])


if __name__ == "__main__":
	main()

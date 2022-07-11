import random

from numpy.random import exponential

class Payment:
	'''
		A payment has amount, fee(s), and the next payment.
	'''
	def __init__(self, ds_payment, fee_policy, amount=None, success=None, delay=None):
		self.ds_payment = ds_payment
		if ds_payment is None:
			# last hop
			assert(amount is not None and success is not None and delay is not None)
			self.amount = amount
			self.upfront_fee = 0
			self.success_fee = 0
			self.delay = delay
			self.success = success
		else:
			# amount is fully deteremined by downstream payment
			self.amount = ds_payment.amount + ds_payment.upfront_fee + ds_payment.success_fee
			self.upfront_fee, self.success_fee = fee_policy.calculate_fees(self.amount)
			self.delay = ds_payment.delay
			self.success = ds_payment.success

	def __str__(self):
		total_fee = self.upfront_fee + self.success_fee
		s = "\nAmount:  " + str(self.amount)
		if self.ds_payment is not None:
			s += "\n  Total fee:	" + str(total_fee) \
			#+ "\n    in %:	" + str(round(100 * total_fee / self.amount))
			s += "\n  upfront fee:	" + str(self.upfront_fee)
			s += "\n  success_fee:	" + str(self.success_fee)
			s += "  \nDownstream payment:"
			s += str(self.ds_payment)
		#s += "\nContains downstream Payment? " + str(self.ds_payment is not None)
		return s


class PaymentGenerator:
	'''
		An abstract class for payment generation.
	'''

	def __init__(self, route, min_amount, max_amount, min_delay, max_delay, prob_fail, exp_time_to_next):
		self.min_amount = min_amount
		self.max_amount = max_amount
		self.min_delay = min_delay
		self.max_delay = max_delay
		self.prob_fail = prob_fail
		self.exp_time_to_next = exp_time_to_next


class HonestPaymentGenerator(PaymentGenerator):
	'''
		Generate the next payment in an honest payment flow.
	'''

	def __init__(self, route, min_amount, max_amount, min_delay, max_delay, prob_fail, exp_time_to_next):
		PaymentGenerator.__init__(self, route, min_amount, max_amount, min_delay, max_delay, prob_fail, exp_time_to_next)

	def generate_random_parameters(self):
		# Payment amount is uniform between the maximal and minimal values
		amount 		= random.randint(self.min_amount, self.max_amount)
		# Payment delay is uniform between the maximal and minimal values
		# FIXME: should it be normally distributed?
		delay 		= random.uniform(self.min_delay, self.max_delay)
		# Payment success comes from a biased coin flip
		success 	= random.random() > self.prob_fail
		# Payment rate is the time from when this payment is initiated to when the next one is initiated
		# We model payment flow as a Poisson process
		# The rate (aka lambda) may be greater than payment delay
		# In that case, the next payment is dropped (the node can't handle it)
		# We implement this on the caller's side
		time_to_next = exponential(self.exp_time_to_next)
		return (amount, delay, success, time_to_next)

	def next(self, route):
		amount, delay, success, time_to_next = self.generate_random_parameters()
		p = Payment(ds_payment=None, fee_policy=None, amount=amount, success=success, delay=delay)
		for node in reversed(route):
			p = Payment(p, node.fee_policy)
		return p, time_to_next


class JamPaymentGenerator(PaymentGenerator):
	'''
		Generate the next jam in a flow of jams.
	'''

	def __init__(self, route, jam_amount, jam_delay):
		PaymentGenerator.__init__(self, route, min_amount = jam_amount, max_amount = jam_amount,
			min_delay = jam_delay, max_delay = jam_delay, prob_fail = 1, exp_time_to_next = jam_delay)

	def next(self, route):
		p = Payment(ds_payment=None, fee_policy=None, amount=self.min_amount, success=False, delay=self.max_delay)
		for node in reversed(route):
			p = Payment(p, node.fee_policy)
		# jams come exactly one after another, without any gap
		# hence the time between jams is the length of a jam (= max_delay)
		return p, self.exp_time_to_next
import random

from numpy.random import exponential

from payment import Payment

class PaymentGenerator:
	'''
		An abstract class for payment generation.
	'''

	def __init__(self, route, min_amount, max_amount, min_delay, expected_extra_delay, 
		prob_fail, expected_time_to_next, num_payments_in_batch):
		self.min_amount = min_amount
		self.max_amount = max_amount
		self.min_delay = min_delay
		self.expected_extra_delay = expected_extra_delay
		self.prob_fail = prob_fail
		self.expected_time_to_next = expected_time_to_next
		self.num_payments_in_batch = num_payments_in_batch


class HonestPaymentGenerator(PaymentGenerator):
	'''
		Generate the next payment in an honest payment flow.
	'''

	def __init__(self, route, min_amount, max_amount, min_delay, expected_extra_delay, prob_fail, expected_time_to_next):
		PaymentGenerator.__init__(self, route, min_amount, max_amount, 
			min_delay, expected_extra_delay, prob_fail, expected_time_to_next,
			num_payments_in_batch=1)

	def generate_random_parameters(self):
		# Payment amount is uniform between the maximal and minimal values
		amount 		= random.randint(self.min_amount, self.max_amount)
		# Payment delay is exponentially distributed and shifted (can't be lower than some minimal delay)
		delay 		= self.min_delay + exponential(self.expected_extra_delay)
		# Payment success comes from a biased coin flip
		success 	= random.random() > self.prob_fail
		# Payment rate is the time from when this payment is initiated to when the next one is initiated
		# We model payment flow as a Poisson process
		# The rate (aka lambda) may be greater than payment delay
		# In that case, the next payment is dropped (the node can't handle it)
		# We implement this on the caller's side
		time_to_next = exponential(self.expected_time_to_next)
		return (amount, delay, success, time_to_next)

	def next(self, route):
		amount, delay, success, time_to_next = self.generate_random_parameters()
		p = Payment(downstream_payment=None, fee_policy=None, amount=amount, delay=delay)
		for node in reversed(route):
			p = Payment(p, node.fee_policy)
		return p, time_to_next


class JamPaymentGenerator(PaymentGenerator):
	'''
		Generate the next jam in a flow of jams.
	'''

	def __init__(self, route, jam_amount, jam_delay, num_payments_in_batch):
		PaymentGenerator.__init__(self, route, min_amount = jam_amount, max_amount = jam_amount,
			min_delay = jam_delay, expected_extra_delay = jam_delay, 
			prob_fail = 1, expected_time_to_next = jam_delay,
			num_payments_in_batch = num_payments_in_batch)
		self.batch_so_far = 0

	def next(self, route):
		p = Payment(downstream_payment=None, fee_policy=None, amount=self.min_amount, delay=self.expected_extra_delay)
		for node in reversed(route):
			p = Payment(p, node.fee_policy)
		# jams within one batch come one after another without any gap
		# there is a fixed-time pause between batches
		self.batch_so_far += 1
		if self.batch_so_far > self.num_payments_in_batch:
			self.batch_so_far = 0
			time_to_next = self.expected_time_to_next
		else:
			time_to_next = 0
		return p, time_to_next
import random

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

	def __init__(self, route, min_amount, max_amount, min_delay, max_delay, prob_fail):
		self.min_amount = min_amount
		self.max_amount = max_amount
		self.min_delay = min_delay
		self.max_delay = max_delay
		self.prob_fail = prob_fail

	def generate_random_parameters(self):
		# All randomness should happen here.
		amount 		= random.randint(self.min_amount, self.max_amount)
		delay 		= random.randint(self.min_delay, self.max_delay)
		success 	= random.random() > self.prob_fail
		return (amount, delay, success)

	def next(self, route):
		amount, delay, success = self.generate_random_parameters()
		p = Payment(ds_payment=None, fee_policy=None, amount=amount, success=success, delay=delay)
		for node in reversed(route):
			p = Payment(p, node.fee_policy)
		return p


class JamPaymentGenerator(PaymentGenerator):

	def __init__(self, route, jam_amount, jam_delay):
		PaymentGenerator.__init__(self, route, min_amount = jam_amount, max_amount = jam_amount,
			min_delay = jam_delay, max_delay = jam_delay, prob_fail = 1)

	def next(self, route):
		p = Payment(ds_payment=None, fee_policy=None, 
			amount=self.min_amount, success=False, delay=self.max_delay)
		for node in reversed(route):
			p = Payment(p, node.fee_policy)
		return p
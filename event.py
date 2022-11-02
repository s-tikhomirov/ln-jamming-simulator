from utils import generate_id

import logging
logger = logging.getLogger(__name__)


class Event:
	'''
		An Event is a planned payment (honest or jam) stored in a Schedule.
	'''

	def __init__(self, sender, receiver, amount, processing_delay, desired_result, must_route_via_nodes=[]):
		assert(sender != receiver)
		# ID is useful for seamless ordering inside the priority queue
		self.id = generate_id()
		self.sender = sender
		self.receiver = receiver
		self.amount = amount
		self.processing_delay = processing_delay
		self.desired_result = desired_result
		self.must_route_via_nodes = must_route_via_nodes

	def __lt__(self, other):
		return self.id < other.id

	def __gt__(self, other):
		return other < self

	def __repr__(self):  # pragma: no cover
		s = str((self.sender, self.receiver, self.amount, self.processing_delay, self.desired_result, self.must_route_via_nodes))
		return s

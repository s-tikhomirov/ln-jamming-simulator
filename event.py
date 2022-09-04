from string import hexdigits
from random import choice

import logging
logger = logging.getLogger(__name__)


class Event:
	'''
		A planned payment stored in a Schedule.
	'''

	def __init__(self, sender, receiver, amount, processing_delay, desired_result, must_route_via_nodes=[]):
		'''
			- sender
				The sender of the payment.

			- receiver
				The receiver of the payment.

			- amount
				The amount the receiver will receive if the payment succeeds.
				(Whether or not to exclude last-hop upfront fee is decided on Payment construction.)

			- processing delay
				How much would it take an HTLC to resolve, IF the corresponding payment reaches the receiver.
				Otherwise, no HTLC is stored, and the delay is zero.

			- desired_result
				True for honest payments, False for jams.

			- must_route_via_nodes
				A tuple of (consecutive) nodes that the payment must be routed through.
		'''
		# ID is useful for seamless ordering inside the priority queue
		assert(sender != receiver)
		self.id = "".join(choice(hexdigits) for i in range(6))
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

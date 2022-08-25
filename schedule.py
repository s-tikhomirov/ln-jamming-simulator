from queue import PriorityQueue
from random import choice
from string import hexdigits

from params import (
	honest_amount_function,
	honest_proccesing_delay_function,
	honest_generation_delay_function,
	ProtocolParams,
	PaymentFlowParams)

import logging
logger = logging.getLogger(__name__)


class Event:
	'''
		A planned payment stored in a Schedule.
	'''

	def __init__(self, sender, receiver, amount, processing_delay, desired_result, must_route_via=[]):
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

			- must_route_via
				A tuple of (consecutive) nodes that the payment must be routed through.
		'''
		# ID is useful for seamless ordering inside the priority queue
		self.id = "".join(choice(hexdigits) for i in range(6))
		self.sender = sender
		self.receiver = receiver
		self.amount = amount
		self.processing_delay = processing_delay
		self.desired_result = desired_result
		self.must_route_via = must_route_via

	def __repr__(self):
		s = str((self.sender, self.receiver, self.amount, self.processing_delay, self.desired_result, self.must_route_via))
		return s

	def __lt__(self, other):
		return self.id < other.id

	def __gt__(self, other):
		return other < self


class Schedule:
	'''
		A schedule of Events (to-be payments) to be executed by a Simulator.
	'''

	def __init__(self, duration=0):
		'''
		- duration
			A timestamp at which to stop Schedule generation.
			Note: this is not the same as the timestamp of the last Event.
			(E.g., for duration 30, the last event may be at timestamp 28.)
		'''
		self.schedule = PriorityQueue()
		self.end_time = duration

	def populate(
		self,
		senders_list,
		receivers_list,
		amount_function,
		desired_result,
		payment_processing_delay_function,
		payment_generation_delay_function,
		must_route_via=[]):
		'''
			- senders_list
				Pick a sender uniformly from this list.

			- receivers_list
				Pick a receiver uniformly from this list.

			- amount_function
				A function to generate each next payment amount.

			- payment_processing_delay_function
				A function to generate each next processing delay (encoded within the payment).

			- payment_generation_delay_function
				A function to generate a delay until the next Event in the Schedule.
		'''
		t = 0
		while t < self.end_time:
			sender = choice(senders_list)
			receiver = choice(receivers_list)
			if sender == receiver:
				continue
			# whether to exclude last-hop upfront fee from amount or not,
			# is decided on Payment construction stage later
			amount = amount_function()
			processing_delay = payment_processing_delay_function()
			event = Event(sender, receiver, amount, processing_delay, desired_result, must_route_via)
			self.put_event(t, event)
			t += payment_generation_delay_function()

	def put_event(self, event_time, event, current_time=-1):
		# prevent inserting events from the past
		assert(current_time < event_time)
		self.schedule.put_nowait((event_time, event))

	def get_event(self):
		# return event time and the event itself
		if self.schedule.empty():
			return None, None
		time, event = self.schedule.get_nowait()
		return time, event

	def get_all_events(self):
		# Only used for debugging.
		# Note: this clears the queue!
		timed_events = []
		while not self.schedule.empty():
			time, event = self.schedule.get_nowait()
			timed_events.append((time, event))
		return timed_events

	def get_size(self):
		return self.schedule.qsize()

	def empty(self):
		return self.schedule.empty()

	def __repr__(self):
		s = "\nSchedule:\n"
		s += "\n".join([str(str(e[0]) + "	" + str(e[1])) for e in self.get_all_events()])
		return s


def generate_honest_schedule(senders_list, receivers_list, duration, must_route_via=[]):
	schedule = Schedule(duration=duration)
	schedule.populate(
		senders_list=senders_list,
		receivers_list=receivers_list,
		amount_function=honest_amount_function,
		desired_result=True,
		payment_processing_delay_function=honest_proccesing_delay_function,
		payment_generation_delay_function=honest_generation_delay_function,
		must_route_via=must_route_via)
	return schedule


def generate_jamming_schedule(duration, must_route_via):
	# sender and receiver are "JammerSender" and "JammerReceiver"
	schedule = Schedule(duration=duration)
	jam_amount = ProtocolParams["DUST_LIMIT"]
	jam_delay = PaymentFlowParams["JAM_DELAY"]
	first_jam = Event(
		sender="JammerSender",
		receiver="JammerReceiver",
		amount=jam_amount,
		processing_delay=jam_delay,
		desired_result=False,
		must_route_via=must_route_via)
	schedule.put_event(0, first_jam)
	return schedule

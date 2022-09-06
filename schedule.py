from queue import PriorityQueue
from random import choice

from event import Event
from params import (
	honest_amount_function,
	honest_proccesing_delay_function,
	honest_generation_delay_function,
	ProtocolParams,
	PaymentFlowParams)

import logging
logger = logging.getLogger(__name__)


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
		must_route_via_nodes=[],
		enforce_dust_limit=False):
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
		while t <= self.end_time:
			sender = choice(senders_list)
			receiver = choice(receivers_list)
			amount = amount_function()
			if sender != receiver and (amount >= ProtocolParams["DUST_LIMIT"] or not enforce_dust_limit):
				# whether to exclude last-hop upfront fee from amount or not,
				# is decided on Payment construction stage later
				processing_delay = payment_processing_delay_function()
				event = Event(sender, receiver, amount, processing_delay, desired_result, must_route_via_nodes)
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

	def is_empty(self):
		return self.schedule.empty()

	def __repr__(self):  # pragma: no cover
		s = "\nSchedule:\n"
		s += "\n".join([str(str(e[0]) + "	" + str(e[1])) for e in self.get_all_events()])
		return s


class HonestSchedule(Schedule):

	def __init__(self, duration=0):
		Schedule.__init__(self, duration)

	def populate(self, senders_list, receivers_list, must_route_via_nodes=[]):
		Schedule.populate(
			self,
			senders_list=senders_list,
			receivers_list=receivers_list,
			amount_function=honest_amount_function,
			desired_result=True,
			payment_processing_delay_function=honest_proccesing_delay_function,
			payment_generation_delay_function=honest_generation_delay_function,
			must_route_via_nodes=must_route_via_nodes)


class JammingSchedule(Schedule):

	def __init__(self, duration=0):
		Schedule.__init__(self, duration)

	def populate(self, one_jam_per_each_of_hops=[], sender="JammerSender", receiver="JammerReceiver"):
		# sender and receiver are "JammerSender" and "JammerReceiver"
		# generate a jamming schedule that assumes that the jammer connects
		# to ALL target nodes (JammerSender->A and B->JammerReceiver)
		# for all directed target edges (A,B)
		jam_amount = ProtocolParams["DUST_LIMIT"]
		jam_delay = PaymentFlowParams["JAM_DELAY"]
		jam_sender = sender
		jam_receiver = receiver
		if one_jam_per_each_of_hops:
			for target_hop in one_jam_per_each_of_hops:
				initial_jam = Event(
					sender=jam_sender,
					receiver=jam_receiver,
					amount=jam_amount,
					processing_delay=jam_delay,
					desired_result=False,
					must_route_via_nodes=target_hop)
				self.put_event(0, initial_jam)
		else:
			initial_jam = Event(
				sender=jam_sender,
				receiver=jam_receiver,
				amount=jam_amount,
				processing_delay=jam_delay,
				desired_result=False)
			self.put_event(0, initial_jam)

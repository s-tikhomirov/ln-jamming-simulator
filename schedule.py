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


class GenericSchedule:
	'''
		A schedule of Events (to-be payments) to be executed by a Simulator.
	'''

	def __init__(self, end_time=0):
		self.end_time = end_time
		self.schedule = PriorityQueue()

	def get_num_events(self):
		return self.schedule.qsize()

	def get_event(self):
		# return event time and the event itself
		if self.schedule.empty():
			return None, None
		time, event = self.schedule.get_nowait()
		return time, event

	def get_all_events(self):
		# Only used for debugging. Note: this clears the queue!
		timed_events = []
		while not self.schedule.empty():
			time, event = self.schedule.get_nowait()
			timed_events.append((time, event))
		return timed_events

	def no_more_events(self):
		return self.schedule.empty()

	def put_event(self, event_time, event, current_time=-1):
		# prohibit inserting events into the past or after end time
		assert current_time < event_time <= self.end_time
		self.schedule.put_nowait((event_time, event))

	def __repr__(self):  # pragma: no cover
		s = "\nSchedule:\n"
		s += "\n".join([str(str(time) + "	" + str(event)) for (time, event) in self.get_all_events()])
		return s


class HonestSchedule(GenericSchedule):

	def __init__(
		self,
		end_time,
		senders,
		receivers,
		amount_function=honest_amount_function,
		desired_result_function=lambda: True,
		payment_processing_delay_function=honest_proccesing_delay_function,
		payment_generation_delay_function=honest_generation_delay_function,
		must_route_via_nodes=[]):
		'''
			- senders
				A list of possible senders.

			- receivers
				A list of possible receivers.

			- amount_function
				Generate the payment amount.

			- desired_result_function
				Generate the desired result (True for honest payments, False for jams).

			- payment_processing_delay_function
				Generate the processing delay (encoded within the payment).

			- payment_generation_delay_function
				Generate the delay until the next Event in the Schedule.

			- must_route_via_nodes
				A tuple of (consecutive) nodes that the payment must be routed through.
		'''
		GenericSchedule.__init__(self, end_time)
		t = 0
		while t <= self.end_time:
			sender = choice(senders)
			receiver = choice(receivers)
			amount = amount_function()
			if sender != receiver:
				# whether to exclude last-hop upfront fee from amount or not,
				# is decided on Payment construction stage later
				processing_delay = payment_processing_delay_function()
				desired_result = desired_result_function()
				event = Event(sender, receiver, amount, processing_delay, desired_result, must_route_via_nodes)
				self.put_event(t, event)
			t += payment_generation_delay_function()


class JammingSchedule(GenericSchedule):

	def __init__(
		self,
		end_time,
		jam_sender="JammerSender",
		jam_receiver="JammerReceiver",
		hop_to_jam_with_own_batch=[]):
		GenericSchedule.__init__(self, end_time)
		jam_amount = ProtocolParams["DUST_LIMIT"]
		jam_delay = PaymentFlowParams["JAM_DELAY"]
		if hop_to_jam_with_own_batch:
			for hop in hop_to_jam_with_own_batch:
				initial_jam = Event(
					sender=jam_sender,
					receiver=jam_receiver,
					amount=jam_amount,
					processing_delay=jam_delay,
					desired_result=False,
					must_route_via_nodes=hop)
				self.put_event(0, initial_jam)
		else:
			initial_jam = Event(
				sender=jam_sender,
				receiver=jam_receiver,
				amount=jam_amount,
				processing_delay=jam_delay,
				desired_result=False)
			self.put_event(0, initial_jam)

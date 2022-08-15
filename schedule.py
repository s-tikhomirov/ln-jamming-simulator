from queue import PriorityQueue
from random import choice
from string import hexdigits

from params import PaymentFlowParams, ProtocolParams, PaymentFlowParams

class Event:
	'''
		An event is a planned Payment that is stored in a Schedule.
	'''
	def __init__(self, sender, receiver, amount, processing_delay, desired_result):
		self.id = "".join(choice(hexdigits) for i in range(6))
		self.sender = sender
		self.receiver = receiver
		self.amount = amount
		self.processing_delay = processing_delay
		self.desired_result = desired_result

	def __repr__(self):
		s = str((self.sender, self.receiver, self.amount, self.processing_delay, self.desired_result))
		return s

	def __lt__(self, other):
		return self.id < other.id

	def __gt__(self, other):
		return other < self


class Schedule:
	'''
		A schedule of Events (to-be payments) to be executed by a Simulator.
	'''
	def __init__(self):
		self.schedule = PriorityQueue()

	def generate_schedule(self,
		senders_list,
		receivers_list,
		amount_function,
		desired_result,
		payment_processing_delay_function,
		payment_generation_delay_function,
		scheduled_duration):
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

			- scheduled_duration
				A timestamp at which to stop Schedule generation.
				Note: this is not the same as the timestamp of the last Event.
				(E.g., for scheduled_duration 30, the last event may be at timestamp 28.)
		'''
		t = 0
		while t < scheduled_duration:
			sender = choice(senders_list)
			receiver = choice(receivers_list)
			if sender == receiver:
				continue
			# whether to exclude last-hop upfront fee from amount or not,
			# is decided on Payment construction stage later
			amount = amount_function()
			processing_delay = payment_processing_delay_function()
			event = Event(sender, receiver, amount, processing_delay, desired_result)
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
		# Only used for printing while debugging.
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
		s += "\n".join([ str(str(e[0]) + "	" + str(e[1])) for e in self.get_all_events()])
		return s

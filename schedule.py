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
		A schedule of events (to-be payments)
		to be executed by Simulator during a simulation
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
		# Generate a list of payments to be processed in the experiment.
		# The difference between honest payments and jams is reflected ONLY here, not in nodes!
		# Desired_result is True for honest payments and False for jams.
		# returns a list (priority queue?) of payments to be executed.
		# for jamming: batches of payments with minimal (zero?) delays, then 7-sec delay
		t = 0
		while t < scheduled_duration:
			sender = choice(senders_list)
			receiver = choice(receivers_list)
			if sender == receiver:
				continue
			amount = amount_function()
			processing_delay = payment_processing_delay_function()
			# exclude last-hop upfront fee is decided later, on Payment construction stage
			# payment construction depends on route
			# therefore we construct routes and Payment objects later
			event = Event(sender, receiver, amount, processing_delay, desired_result)
			self.put_event(t, event)
			t += payment_generation_delay_function()

	def put_event(self, event_time, event, current_time=-1):
		# can't insert events that would execute in the past
		assert(current_time < event_time)
		self.schedule.put_nowait((event_time, event))

	def get_event(self):
		# return event time and the event itself
		if self.schedule.empty():
			return None, None
		time, event = self.schedule.get_nowait()
		return time, event

	def get_all_events(self):
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
		# NB: this clears the queue!
		s = "\nSchedule:\n"
		s += "\n".join([ str(str(e[0]) + "	" + str(e[1])) for e in self.get_all_events()])
		return s


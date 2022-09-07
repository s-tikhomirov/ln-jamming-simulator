import logging
logger = logging.getLogger(__name__)


class Direction:

	def __init__(self, u_node, d_node):
		assert(u_node != d_node)
		self.direction = u_node < d_node

	def __hash__(self):
		return hash(self.direction)

	def __eq__(self, other):
		return self.direction == other.direction

	def __ne__(self, other):
		return not(self == other)

	def __repr__(self):
		assert(self == Direction.Alph or self == Direction.NonAlph)
		if self == Direction.Alph:
			return "Alph"
		elif self == Direction.NonAlph:
			return "NonAlph"


Direction.Alph = Direction("a", "b")
Direction.NonAlph = Direction("b", "a")

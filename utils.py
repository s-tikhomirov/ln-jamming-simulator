from string import hexdigits
from random import choice


import logging
logger = logging.getLogger(__name__)


def generate_id(length=6):
	return "".join(choice(hexdigits) for i in range(length))

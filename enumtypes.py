from enum import Enum


class ErrorType(Enum):
	LOW_BALANCE = "no_balance"
	NO_SLOTS = "no_slots"
	FAILED_DELIBERATELY = "failed_deliberately"


class FeeType(Enum):
	UPFRONT = "upfront"
	SUCCESS = "success"

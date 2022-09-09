from enum import Enum


class ErrorType(Enum):
	LOW_BALANCE = "no_balance"
	NO_SLOTS = "no_slots"
	LOW_FEE = "low_fee"
	FAILED_DELIBERATELY = "failed_deliberately"


class FeeType(Enum):
	UPFRONT = "upfront"
	SUCCESS = "success"

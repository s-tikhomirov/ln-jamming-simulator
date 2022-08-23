from math import log
from numpy.random import exponential, lognormal

K = 1000
M = K * K


def generic_fee_function(base, rate, amount):
	return base + rate * amount


def honest_amount_function():
	return lognormal(mean=PaymentFlowParams["AMOUNT_MU"], sigma=PaymentFlowParams["AMOUNT_SIGMA"])


def honest_proccesing_delay_function():
	return PaymentFlowParams["MIN_DELAY"] + exponential(PaymentFlowParams["EXPECTED_EXTRA_DELAY"])


def honest_generation_delay_function():
	return exponential(PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"])


PaymentFlowParams = {
	# Amounts follow log-normal distribution
	# Cf. https://swiftinstitute.org/wp-content/uploads/2012/10/The-Statistics-of-Payments_v15.pdf
	# mu is the natural log of the mean amount (we assume 50k sats ~ $10 at $20k per BTC)
	# sigma is the measure of how spread out the distribution is
	# with sigma : 0.7, maximum values are around 1 million; values above ~300k are rare
	"AMOUNT_MU": log(50 * K),
	"AMOUNT_SIGMA": 0.7,

	# average payment resolution time was 3-4 seconds in 2020:
	# https://arxiv.org/abs/2004.00333 (Section 4.4)
	"MIN_DELAY": 1,
	"EXPECTED_EXTRA_DELAY": 3,
	"JAM_DELAY": 7,

	# in terms of exponential distribution, this is beta
	# (aka scale, aka the inverse of rate lambda)
	"HONEST_PAYMENT_EVERY_SECONDS": 10,

	# the probability that a payment fails at a hop
	# because the _next_ channel can't handle it (e.channel_graph., low balance)
	#"PROB_NEXT_CHANNEL_LOW_BALANCE" : 0.05,
}

ProtocolParams = {
	# all payment amounts (on every layer) must be higher than dust limit
	# (otherwise HTLCs are trimmed)
	# we use the value 354 ("unknown segwit versions")
	# https://github.com/lightning/bolts/blob/master/03-transactions.md#dust-limits
	"DUST_LIMIT": 354,

	# max_accepted_htlcs is limited to 483 to ensure that,
	# even if both sides send the maximum number of HTLCs,
	# the commitment_signed message will still be under the maximum message size.
	# It also ensures that a single penalty transaction can spend
	# the entire commitment transaction, as calculated in BOLT #5.
	# https://github.com/lightning/bolts/blob/master/02-peer-protocol.md#rationale-7
	"NUM_SLOTS": 483
}


FeeParams = {
	# LN implementations use the following default values for base / rate:
	# LND: 1 sat / 1 per million
	# https://docs.lightning.engineering/lightning-network-tools/lnd/channel-fees
	# https://github.com/lightningnetwork/lnd/blob/master/sample-lnd.conf
	# Core Lightning: 1 sat / 10 per million
	# https://lightning.readthedocs.io/lightningd-config.5.html#lightning-node-customization-options
	# Eclair: ?
	# LDK: ?
	# Let's use _success-case_ fees similar to currently used ones,
	# and vary the _upfront-case_ fees across experiments

	"SUCCESS_BASE": 1,
	"SUCCESS_RATE": 5 / M
}

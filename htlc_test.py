from htlc import InFlightHtlc


def test_htlc_creation():
	htlc = InFlightHtlc(payment_id="pid1", success_fee=100, desired_result=True)
	assert(htlc.payment_id == "pid1")
	assert(htlc.success_fee == 100)
	assert(htlc.desired_result is True)


def test_htlc_compare():
	htlc_1 = InFlightHtlc(payment_id="pid1", success_fee=100, desired_result=True)
	htlc_2 = InFlightHtlc(payment_id="pid2", success_fee=100, desired_result=True)
	assert(htlc_1 < htlc_2)
	assert((htlc_1 > htlc_2) != (htlc_1 < htlc_2))

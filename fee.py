class FeePolicy:

	def __init__(self):
		pass

	def calculate_fees(self):
		raise NotImplementedError


class LinearFeePolicy(FeePolicy):

	def __init__(self, base_fee, prop_fee_share, upfront_fee_share):
		self.base_fee = base_fee
		self.prop_fee_share = prop_fee_share
		self.upfront_fee_share = upfront_fee_share
		FeePolicy.__init__(self)

	def calculate_total_fee(self, amount):
		total_fee = round(self.base_fee + self.prop_fee_share * amount)
		if total_fee > amount:
			raise Exception("Total fee is " + str(total_fee) + " > " + str(amount))
		return total_fee

	def calculate_fees(self, amount):
		total_fee = self.calculate_total_fee(amount)
		upfront_fee = round(total_fee * self.upfront_fee_share)
		success_fee = total_fee - upfront_fee
		return upfront_fee, success_fee
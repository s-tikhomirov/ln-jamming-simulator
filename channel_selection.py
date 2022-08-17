from channel import ChannelDirection, dir0, dir1

# Functions for selecting a channel in a hop for given criteria.
# (More precisely, a channel direction.)
# Selection involves three steps: 1. filter; 2. sort; 3. take top element.


# FILTER

# We MUST NOT check for free slots here: some may be occupied with outdated in-flight payments!
# We would only resolve those HTLCs inside payment handling.

def filter_dirs_in_hop(channels_dict, amount, direction, is_suitable):
	# Return only ch_dirs from a hop that are suitable as per is_suitable function.
	suitable_ch_dirs = [
		(cid, ch["directions"][direction]) for cid, ch in channels_dict.items()
		if is_suitable(ch["directions"][direction])]
	return suitable_ch_dirs


def sort_filtered_ch_dirs(filtered_ch_dirs, sorting_function):
	# Sort ch_dirs as per a given sorting function.
	return sorted(filtered_ch_dirs, key=sorting_function)


def lowest_fee_enabled_channel(channels_dict, amount, direction):

	def ch_dir_enabled(ch_dir):
		is_enabled = ch_dir.is_enabled if ch_dir is not None else False
		return is_enabled
	filtered_ch_dirs = filter_dirs_in_hop(channels_dict, amount, direction, is_suitable=ch_dir_enabled)

	def total_fee(ch_dir, amount):
		success_fee = ch_dir.success_fee_function(amount)
		upfront_fee = ch_dir.upfront_fee_function(amount + success_fee)
		return success_fee + upfront_fee
	sorted_filtered_ch_dirs = sort_filtered_ch_dirs(
		filtered_ch_dirs,
		sorting_function=lambda cid_ch_dir: total_fee(cid_ch_dir[1], amount))
	chosen_cid, ch_dir = sorted_filtered_ch_dirs[0]
	return chosen_cid, ch_dir

from channel import ChannelDirection, dir0, dir1

# Functions for selecting a channel in a hop for given criteria.
# (More precisely, a channel direction.)
# Selection involves three steps: 1. filter; 2. sort; 3. take top element.

#### FILTER ####

def filter_dirs_in_hop(channels_dict, amount, direction, is_suitable):
	suitable_ch_dirs = [(cid,ch["directions"][direction]) for cid,ch in channels_dict.items() \
	if is_suitable(ch["directions"][direction])]
	return suitable_ch_dirs

def ch_dir_enabled(ch_dir):
	is_enabled = ch_dir.is_enabled if ch_dir is not None else False
	return is_enabled

# We MUST NOT check for free slots here: some may be occupied with outdated in-flight payments!
# We would only resolve those HTLCs inside payment handling.

def has_min_capacity(channels_dict, cid, min_capacity):
	return channels_dict[cid]["capacity"] >= min_capacity



#### SORT ####

lambda cid_ch_dir: total_fee(cid_ch_dir[1])

def sort_filtered_ch_dirs(filtered_ch_dirs, sorting_function):
	return sorted(filtered_ch_dirs, key=sorting_function)

def total_fee(ch_dir, amount):
	# TODO: make sure amount vs body is used correctly here
	success_fee = ch_dir.success_fee_function(amount)
	upfront_fee = ch_dir.upfront_fee_function(amount + success_fee)
	return success_fee + upfront_fee


#### CONCRETE USE CASES ####

def lowest_fee_enabled_channel(channels_dict, amount, direction):
	filtered_ch_dirs = filter_dirs_in_hop(channels_dict, amount, direction, is_suitable = ch_dir_enabled)
	sorted_filtered_ch_dirs = sort_filtered_ch_dirs(filtered_ch_dirs, sorting_function = lambda cid_ch_dir : total_fee(cid_ch_dir[1], amount))
	chosen_cid, ch_dir = sorted_filtered_ch_dirs[0]
	#print("Chosen cid:", chosen_cid)
	return chosen_cid, ch_dir

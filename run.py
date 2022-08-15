from simulator import Simulator
from schedule import Schedule, Event
from lnmodel import LNModel, RevenueType

from params import honest_amount_function, honest_proccesing_delay_function, honest_generation_delay_function
from params import ProtocolParams, PaymentFlowParams, FeeParams

import json
import csv
from statistics import mean
from time import time
import argparse

channel_ABx0 = {
	"source": "Alice",
	"destination": "Bob",
	"short_channel_id": "ABx0",
	"satoshis": 1000000,
	"active": True,
	"base_fee_millisatoshi": 1000,
	"fee_per_millionth": 5,
	"base_fee_millisatoshi_upfront": 0,
	"fee_per_millionth_upfront": 0
	}
channel_BCx0 = {
	"source": "Bob",
	"destination": "Charlie",
	"short_channel_id": "BCx0",
	"satoshis": 1000000,
	"active": True,
	"base_fee_millisatoshi": 1000,
	"fee_per_millionth": 5,
	"base_fee_millisatoshi_upfront": 0,
	"fee_per_millionth_upfront": 0
	}
channel_CDx0 = {
	"source": "Charlie",
	"destination": "Dave",
	"short_channel_id": "CDx0",
	"satoshis": 1000000,
	"active": True,
	"base_fee_millisatoshi": 1000,
	"fee_per_millionth": 5,
	"base_fee_millisatoshi_upfront": 0,
	"fee_per_millionth_upfront": 0
}
snapshot_json = {"channels" : [channel_ABx0, channel_BCx0, channel_CDx0]}

SUCCESS_FEE_BASE = FeeParams["SUCCESS_BASE"]
SUCCESS_FEE_RATE = FeeParams["SUCCESS_RATE"]
NUM_SLOTS = ProtocolParams["NUM_SLOTS"]

NO_BALANCE_FAILURES = False
KEEP_RECEIVER_UPFRONT_FEE = True

def run_simulation_honest(ln_model, simulation_duration, num_simulations, 
	no_balance_failures, keep_receiver_upfront_fee):
	print("  Strating honest")
	sim = Simulator(ln_model)
	tmp_revenues = {"Alice" : [], "Bob" : [], "Charlie": [], "Dave": []}
	for i in range(num_simulations):
		print("    Simulation", i + 1, "of", num_simulations)
		for n, m in (("Alice", "Bob"), ("Bob", "Charlie"), ("Charlie", "Dave")):
			ln_model.set_num_slots("Alice", "Bob", NUM_SLOTS)
		sch_honest = Schedule()
		sch_honest.generate_schedule(
			senders_list = ["Alice"],
			receivers_list = ["Dave"],
			amount_function = honest_amount_function,
			desired_result = True,
			payment_processing_delay_function = honest_proccesing_delay_function,
			payment_generation_delay_function = honest_generation_delay_function,
			scheduled_duration = simulation_duration)
		num_events = sim.execute_schedule(sch_honest, 
			no_balance_failures=no_balance_failures,
			keep_receiver_upfront_fee=keep_receiver_upfront_fee,
			simulation_end = simulation_duration)
		print("Handled events:", num_events)
		for node in ("Alice", "Bob", "Charlie", "Dave"):
			upfront_revenue = ln_model.get_revenue(node, RevenueType.UPFRONT)
			success_revenue = ln_model.get_revenue(node, RevenueType.SUCCESS)
			total_revenue = upfront_revenue + success_revenue
			tmp_revenues[node].append(total_revenue)
		ln_model.reset(NUM_SLOTS)
	revenues = {}
	for node in ("Alice", "Bob", "Charlie", "Dave"):
		revenues[node] = mean(tmp_revenues[node])
	return num_events, revenues

def run_simulation_jamming(ln_model, simulation_duration, num_simulations,
	no_balance_failures, keep_receiver_upfront_fee):
	print("  Strating jamming")
	sim = Simulator(ln_model)
	tmp_revenues = {"Alice" : [], "Bob" : [], "Charlie": [], "Dave": []}
	for i in range(num_simulations):
		ln_model.set_num_slots("Alice", "Bob", 		2 * NUM_SLOTS)
		ln_model.set_num_slots("Bob", "Charlie", 		NUM_SLOTS)
		ln_model.set_num_slots("Charlie", "Dave", 	2 *	NUM_SLOTS)
		print("    Simulation", i + 1, "of", num_simulations)
		sch_jamming = Schedule()
		first_jam = Event("Alice", "Dave", 
			amount = ProtocolParams["DUST_LIMIT"],
			processing_delay = PaymentFlowParams["MIN_DELAY"] + 2 * PaymentFlowParams["EXPECTED_EXTRA_DELAY"],
			desired_result = False)
		sch_jamming.put_event(0, first_jam)
		num_events = sim.execute_schedule(sch_jamming,
			target_node_pair = ("Bob", "Charlie"),
			jam_with_insertion = True,
			no_balance_failures=no_balance_failures,
			keep_receiver_upfront_fee=keep_receiver_upfront_fee,
			simulation_end = simulation_duration)
		print("Handled events:", num_events)
		for node in ("Alice", "Bob", "Charlie", "Dave"):
			upfront_revenue = ln_model.get_revenue(node, RevenueType.UPFRONT)
			success_revenue = ln_model.get_revenue(node, RevenueType.SUCCESS)
			total_revenue = upfront_revenue + success_revenue
			tmp_revenues[node].append(total_revenue)
		ln_model.reset(NUM_SLOTS)
	revenues = {}
	for node in ("Alice", "Bob", "Charlie", "Dave"):
		revenues[node] = mean(tmp_revenues[node])
	return num_events, revenues

def run_simulation_pair(ln_model, upfront_base_coeff, upfront_rate_coeff,
	simulation_duration, num_simulations,
	no_balance_failures, keep_receiver_upfront_fee):
	print("\nStarting simulation pair")
	for node_1, node_2 in (("Alice", "Bob"), ("Bob", "Charlie"), ("Charlie", "Dave")):
		ln_model.set_fee_function(node_1, node_2, RevenueType.UPFRONT, SUCCESS_FEE_BASE * upfront_base_coeff, SUCCESS_FEE_RATE * upfront_rate_coeff)
		ln_model.set_fee_function(node_1, node_2, RevenueType.SUCCESS, SUCCESS_FEE_BASE, SUCCESS_FEE_RATE)
	revenues = {"honest" : {}, "jamming": {}}
	num_honest_payments, revenues["honest"] = run_simulation_honest(ln_model, simulation_duration, num_simulations, no_balance_failures, keep_receiver_upfront_fee)
	num_jams, revenues["jamming"] = run_simulation_jamming(ln_model, simulation_duration, num_simulations, no_balance_failures, keep_receiver_upfront_fee)
	return num_honest_payments, num_jams, revenues

def run_simulation_series(ln_model, upfront_base_coeff_range, upfront_rate_coeff_range, simulation_duration, num_simulations,
	no_balance_failures, keep_receiver_upfront_fee):
	results = []
	for upfront_base_coeff in upfront_base_coeff_range:
		for upfront_rate_coeff in upfront_rate_coeff_range:
			num_honest_payments, num_jams, revenues = \
			run_simulation_pair(ln_model, upfront_base_coeff, upfront_rate_coeff, simulation_duration, num_simulations,
				no_balance_failures, keep_receiver_upfront_fee)
			result = {
			"upfront_base_coeff": upfront_base_coeff,
			"upfront_rate_coeff": upfront_rate_coeff,
			"num_honest_payments": num_honest_payments, 
			"num_jams": num_jams,
			"revenues": revenues }
			results.append(result)
	return results

def results_to_json_file(results, timestamp):
	with open("results/" + timestamp + "-results" +".json", "w", newline="") as f:
		json.dump(results, f, indent=4)

def results_to_csv_file(results, timestamp):
	with open("results/" + timestamp + "-results" +".csv", "w", newline="") as f:
		writer = csv.writer(f, delimiter = ",", quotechar="'", quoting=csv.QUOTE_MINIMAL)
		writer.writerow(["num_simulations", str(results["num_simulations"])])
		writer.writerow(["simulation_duration", str(results["simulation_duration"])])
		writer.writerow(["success_base", str(results["success_fee_base"])])
		writer.writerow(["success_rate", str(results["success_fee_rate"])])
		writer.writerow(["no_balance_failures", NO_BALANCE_FAILURES])
		writer.writerow(["keep_receiver_upfront_fee", KEEP_RECEIVER_UPFRONT_FEE])
		writer.writerow(["honest_payment_every_seconds", str(PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"])])
		writer.writerow("")
		writer.writerow([
			"upfront_base_coeff",
			"upfront_rate_coeff",
			"num_honest_payments",
			"num_jams",
			"a_h_revenue",
			"a_j_revenue",
			"b_h_revenue",
			"b_j_revenue",
			"c_h_revenue",
			"c_j_revenue",
			"d_h_revenue",
			"d_j_revenue"
			])
		for result in results["results"]:
			writer.writerow([
				result["upfront_base_coeff"],
				result["upfront_rate_coeff"],
				result["num_honest_payments"],
				result["num_jams"],
				result["revenues"]["honest"]["Alice"],
				result["revenues"]["jamming"]["Alice"],
				result["revenues"]["honest"]["Bob"],
				result["revenues"]["jamming"]["Bob"],
				result["revenues"]["honest"]["Charlie"],
				result["revenues"]["jamming"]["Charlie"],
				result["revenues"]["honest"]["Dave"],
				result["revenues"]["jamming"]["Dave"]
				])

def run_all_simulations(simulation_duration, num_simulations,
	no_balance_failures, keep_receiver_upfront_fee,
	upfront_base_coeff_range, upfront_rate_coeff_range):
	ln_model = LNModel(snapshot_json, default_num_slots = ProtocolParams["NUM_SLOTS"])
	results = run_simulation_series(ln_model, upfront_base_coeff_range, upfront_rate_coeff_range,
		simulation_duration, num_simulations, no_balance_failures, keep_receiver_upfront_fee)
	all_results = {
	"simulation_duration": simulation_duration,
	"num_simulations": num_simulations,
	"success_fee_base": SUCCESS_FEE_BASE,
	"success_fee_rate": SUCCESS_FEE_RATE,
	"no_balance_failures": NO_BALANCE_FAILURES,
	"keep_receiver_upfront_fee": KEEP_RECEIVER_UPFRONT_FEE,
	"honest_payment_every_seconds": PaymentFlowParams["HONEST_PAYMENT_EVERY_SECONDS"],
	"results": sorted(results, key = lambda d: (d["upfront_base_coeff"], d["upfront_rate_coeff"]), reverse = False)
	}
	return all_results


DEFAULT_UPFRONT_BASE_COEFF_RANGE = [0, 0.001, 0.002, 0.005, 0.01]
DEFAULT_UPFRONT_RATE_COEFF_RANGE = [0, 0.1, 0.2, 0.5, 1]

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--simulation_duration", default=60, type=int,
		help="Simulation duration in seconds.")
	parser.add_argument("--num_simulations", default=10, type=int,
		help="The number of simulation runs per parameter combinaiton.")
	parser.add_argument('--no_balance_failures', dest='no_balance_failures', default=False, action='store_true')
	parser.add_argument('--keep_receiver_upfront_fee', dest='keep_receiver_upfront_fee', default=True, action='store_true')
	parser.add_argument("--upfront_base_coeff_range",
		nargs="*",
		type=float,
		default=DEFAULT_UPFRONT_BASE_COEFF_RANGE,
		help="A list of values for upfront base fee coefficient.")
	parser.add_argument("--upfront_rate_coeff_range",
		nargs="*",
		type=float,
		default=DEFAULT_UPFRONT_RATE_COEFF_RANGE,
		help="A list of values for upfront base fee coefficient.")
	parser.add_argument("--seed", type=int,
		help="Seed for randomness initialization.")
	args = parser.parse_args()

	if args.seed is not None:
		print("Initializing randomness seed:", args.seed)
		random.seed(args.seed)
		np.random.seed(args.seed)

	start_time = time()
	all_results = run_all_simulations(args.simulation_duration, args.num_simulations,
		args.no_balance_failures, args.keep_receiver_upfront_fee,
		args.upfront_base_coeff_range, args.upfront_rate_coeff_range)
	end_time = time()
	running_time = end_time - start_time
	results_to_json_file(all_results, str(int(end_time)))
	results_to_csv_file(all_results, str(int(end_time)))
	print("\nRunning time (min):", round(running_time / 60, 1))


if __name__ == "__main__":
	main()

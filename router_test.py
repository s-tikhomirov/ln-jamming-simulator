from lnmodel import LNModel
from router import Router

import json
import pytest

import logging
logger = logging.getLogger(__name__)

ROUTER_TEST_SNAPSHOT_FILENAME = "./snapshots/listchannels_router_test.json"
ROUTER_REAL_SNAPSHOT_FILENAME = "./snapshots/listchannels-2021-12-09.json"

AMOUNT = 100


def get_router(snapshot_file):
	print("Parsing JSON file...", snapshot_file)
	with open(snapshot_file, "r") as snapshot_file:
		snapshot_json = json.load(snapshot_file)
	ln_model = LNModel(snapshot_json, default_num_slots=2, no_balance_failures=True, keep_receiver_upfront_fee=True)
	router = Router(ln_model, AMOUNT)
	return router


@pytest.fixture
def example_ln_router():
	return get_router(ROUTER_TEST_SNAPSHOT_FILENAME)


@pytest.fixture
def real_ln_router():
	return get_router(ROUTER_REAL_SNAPSHOT_FILENAME)


def test_get_routes_via_target_hops(example_ln_router):
	print("in test")
	router = example_ln_router
	target_hops = [("Alice", "Bob"), ("Charlie", "Dave"), ("Elon", "Fred")]
	routes = router.get_routes_via_target_hops(
		"Sender",
		"Receiver",
		target_hops,
		min_target_hops_per_route=1,
		max_target_hops_per_route=len(target_hops))
	routes_list = [r for r in routes]
	print(routes_list)
	assert(["Sender", "Alice", "Bob", "Charlie", "Dave", "Receiver"] in routes_list)
	assert(["Sender", "Alice", "Bob", "Receiver"] in routes_list)
	assert(["Sender", "Charlie", "Dave", "Receiver"] in routes_list)
	assert(["Sender", "Elon", "Fred", "Receiver"] in routes_list)


'''
def test_routes_real(real_ln_router):
	router = real_ln_router
	target_node = "03abf6f44c355dec0d5aa155bdbdd6e0c8fefe318eff402de65c6eb2e1be55dc3e"
	in_edges = list(router.ln_model.routing_graph.in_edges(target_node, data=False))
	out_edges = list(router.ln_model.routing_graph.out_edges(target_node, data=False))
	n = 3
	target_hops = in_edges[:n] + out_edges[:n]
	print(len(target_hops))
	sender = "030c3f19d742ca294a55c00376b3b355c3c90d61c6b6b39554dbc7ac19b141c14f"
	receiver = "03c2abfa93eacec04721c019644584424aab2ba4dff3ac9bdab4e9c97007491dda"
	g = router.g
	assert(sender in g)
	assert(receiver in g)
	assert(target_node in g)
	assert(target_hop[0] in g and target_hop[1] in g for target_hop in target_hops)
	#return True
	routes = router.get_routes_via_target_hops(
		sender,
		receiver,
		target_hops,
		min_target_hops_per_route=1,
		max_target_hops_per_route=3)
	routes_list = [r for r in routes]
	logger.info(routes_list)
	logger.info(f"{len(routes_list)} routes generated")
	# 156 routes generated
	# this test was written primarily to check what the compute time would be
	# TODO: do we want to actually assert anything here?
'''

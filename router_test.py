import json
import pytest

from lnmodel import LNModel
from router import Router

import logging
logger = logging.getLogger(__name__)

ROUTER_TEST_SNAPSHOT_FILENAME = "./snapshots/listchannels_router_test.json"
ROUTER_REAL_SNAPSHOT_FILENAME = "./snapshots/listchannels-2021-12-09.json"
WHEEL_SNAPSHOT_FILENAME = "./snapshots/listchannels_wheel.json"

AMOUNT = 100


def get_ln_model(snapshot_file):
	with open(snapshot_file, "r") as snapshot_file:
		snapshot_json = json.load(snapshot_file)
	ln_model = LNModel(snapshot_json, default_num_slots_per_channel_in_direction=2, no_balance_failures=True)
	return ln_model


def test_get_routes_via_target_hops_simple():
	ln_model = get_ln_model(ROUTER_TEST_SNAPSHOT_FILENAME)
	router = Router(ln_model, AMOUNT, "Sender", "Receiver")
	target_hops = [("Alice", "Bob"), ("Charlie", "Dave"), ("Elon", "Fred")]
	router.update_route_generator(target_hops)
	routes_list = [r for r in router.routes]
	print(routes_list)
	assert(("Sender", "Alice", "Bob", "Charlie", "Dave", "Receiver") in routes_list)
	assert(("Sender", "Alice", "Bob", "Receiver") in routes_list)
	assert(("Sender", "Charlie", "Dave", "Receiver") in routes_list)
	assert(("Sender", "Elon", "Fred", "Receiver") in routes_list)


# WHEEL-BASED TESTS #


@pytest.fixture
def wheel_ln_model_with_jammers_channels():
	ln_model = get_ln_model(WHEEL_SNAPSHOT_FILENAME)
	ln_model.add_jammers_channels(
		send_to_nodes=["Alice"],
		receive_from_nodes=["Dave"],
		num_slots=(ln_model.default_num_slots_per_channel_in_direction + 1) * 5)
	return ln_model


@pytest.fixture
def wheel_router(wheel_ln_model_with_jammers_channels):
	return Router(
		ln_model=wheel_ln_model_with_jammers_channels,
		amount=AMOUNT,
		sender="JammerSender",
		receiver="JammerReceiver")


def test_routes_wheel(wheel_router):
	target_hops = [("Hub", "Bob"), ("Alice", "Hub"), ("Charlie", "Hub"), ("Hub", "Dave")]
	wheel_router.update_route_generator(target_hops, allow_repeated_hops=False)
	routes_list = [r for r in wheel_router.routes]
	logger.debug(f"{routes_list}")
	assert(routes_list[0] == ("JammerSender", "Alice", "Hub", "Bob", "Charlie", "Hub", "Dave", "JammerReceiver"))
	logger.info(routes_list)


def test_pre_calculate_paths(wheel_router):
	logger.debug(f"{wheel_router.paths_from_sender}")
	paths_s = wheel_router.paths_from_sender
	assert(paths_s["JammerSender"] == ["JammerSender"])
	assert(paths_s["Alice"] == ["JammerSender", "Alice"])
	assert(paths_s["Bob"] == ["JammerSender", "Alice", "Hub", "Bob"])
	assert(paths_s["Charlie"] == ["JammerSender", "Alice", "Hub", "Bob", "Charlie"])
	assert(paths_s["Dave"] == ["JammerSender", "Alice", "Hub", "Dave"])
	logger.debug(f"{wheel_router.paths_to_receiver}")
	paths_r = wheel_router.paths_to_receiver
	assert(paths_r["JammerSender"] == ["JammerSender", "Alice", "Hub", "Dave", "JammerReceiver"])
	assert(paths_r["Alice"] == ["Alice", "Hub", "Dave", "JammerReceiver"])
	assert(paths_r["Bob"] == ["Bob", "Charlie", "Hub", "Dave", "JammerReceiver"])
	assert(paths_r["Charlie"] == ["Charlie", "Hub", "Dave", "JammerReceiver"])
	assert(paths_r["Dave"] == ["Dave", "JammerReceiver"])
	assert(paths_r["JammerReceiver"] == ["JammerReceiver"])


def test_get_shortest_route_via_hops(wheel_router):
	permutation1 = (("Alice", "Hub"), ("Hub", "Bob"))
	full_route = ("JammerSender", "Alice", "Hub", "Bob", "Charlie", "Hub", "Dave", "JammerReceiver")
	wheel_router.update_route_generator(target_hops=permutation1, max_route_length=len(full_route))
	route = wheel_router.get_route()
	assert(route == full_route)
	permutation2 = (("Alice", "Hub"), ("Hub", "Dave"))
	wheel_router.update_route_generator(target_hops=permutation2, max_route_length=None)
	route = wheel_router.get_route()
	assert(route == ("JammerSender", "Alice", "Hub", "Dave", "JammerReceiver"))


def test_get_routes_via_target_hops(wheel_router):
	target_hops = [("Alice", "Hub"), ("Hub", "Bob"), ("Charlie", "Hub"), ("Hub", "Dave")]
	full_route = ("JammerSender", "Alice", "Hub", "Bob", "Charlie", "Hub", "Dave", "JammerReceiver")
	short_route = ("JammerSender", "Alice", "Hub", "Dave", "JammerReceiver")
	wheel_router.update_route_generator(target_hops, max_route_length=len(full_route))
	route_list = [r for r in wheel_router.routes]
	logger.debug(f"{len(route_list)} {route_list}")
	assert(len(route_list) == 2)
	assert(full_route in route_list)
	assert(short_route in route_list)
	wheel_router.update_route_generator(target_hops, max_route_length=len(short_route))
	route_list = [r for r in wheel_router.routes]
	assert(route_list == [short_route])


def test_is_hop_in_path():
	a, b, c, d = "Alice", "Bob", "Charlie", "Dave"
	path = [a, b, c, d]
	target_hop = b, c
	not_target_hop = c, b
	assert(Router.is_hop_in_path(target_hop, path))
	assert(not Router.is_hop_in_path(not_target_hop, path))


def test_is_permutation_in_path():
	a, b, c, d, e = "Alice", "Bob", "Charlie", "Dave", "Elon"
	path = [a, b, c, d]
	assert(Router.is_permutation_in_path((), path))
	# note trailing comma!
	assert(Router.is_permutation_in_path(((a, b),), path))
	assert(Router.is_permutation_in_path(((b, c), (c, d)), path))
	assert(Router.is_permutation_in_path(((a, b), (b, c)), path))
	assert(Router.is_permutation_in_path(((a, b), (b, c), (c, d)), path))
	assert(not Router.is_permutation_in_path(((b, a),), path))
	assert(not Router.is_permutation_in_path(((b, c), (d, e)), path))
	assert(not Router.is_permutation_in_path(((b, c), (a, b)), path))


def test_first_permutation_element_index_not_in_path():
	a, b, c, d = "Alice", "Bob", "Charlie", "Dave"
	path = [a, b, c]
	assert(Router.first_permutation_element_index_not_in_path(((a, b), (c, d)), path) == 1)
	assert(Router.first_permutation_element_index_not_in_path(((c, d),), path) == 0)
	assert(Router.first_permutation_element_index_not_in_path((), path) is None)
	# (a, b) appears in the route BEFORE (b, c)
	# therefore, the permutation does NOT appear in the route, althrough its individual hops do
	# the order is important: the route contains permutation ((a, b), (b, c))
	# but does NOT contain permutation ((b, c), (a, b))
	# in other words, permutation element at index 1, which is (a, b),
	# is the first to violate the order of permutation inside the route
	assert(Router.first_permutation_element_index_not_in_path(((b, c), (a, b)), path) == 1)


def test_discard_route_with_repeated_hop(wheel_router):
	target_hops = [("Hub", "Bob"), ("Alice", "Hub"), ("Charlie", "Hub"), ("Hub", "Dave")]
	wheel_router.update_route_generator(target_hops, allow_repeated_hops=False)
	routes_list = [r for r in wheel_router.routes]
	logger.debug(f"{routes_list}")
	assert(all(not Router.has_repeated_hop(r) for r in routes_list))
	assert(len(routes_list) == len(set(routes_list)))


def test_shorten_ids():
	route = ["aaaa", "bbbb"]
	assert(Router.shorten_ids(route, length=2) == ["aa", "bb"])


'''
def test_routes_real():
	ln_model = get_ln_model(ROUTER_REAL_SNAPSHOT_FILENAME)
	node_bitrefill = "030c3f19d742ca294a55c00376b3b355c3c90d61c6b6b39554dbc7ac19b141c14f"
	node_tippinme = "03c2abfa93eacec04721c019644584424aab2ba4dff3ac9bdab4e9c97007491dda"
	sender, receiver = node_bitrefill, node_tippinme
	router = Router(ln_model, AMOUNT, sender, receiver)
	target_node = "03abf6f44c355dec0d5aa155bdbdd6e0c8fefe318eff402de65c6eb2e1be55dc3e"
	in_edges = list(router.ln_model.routing_graph.in_edges(target_node, data=False))
	out_edges = list(router.ln_model.routing_graph.out_edges(target_node, data=False))
	n = 4
	max_route_length = 5
	target_hops = in_edges[:n] + out_edges[:n]
	logger.debug(f"Selected {len(target_hops)} target hops")
	router.update_route_generator(target_hops, max_route_length=max_route_length)
	routes_list = [r for r in router.routes]
	assert(all(r[0] == sender and r[-1] == receiver for r in routes_list))
	assert(len(r) <= max_route_length for r in routes_list)
	logger.debug(f"Found {len(routes_list)} routes with length up to {max_route_length}")
	logger.debug(f"{[Router.shorten_ids(r) for r in routes_list]}")
'''

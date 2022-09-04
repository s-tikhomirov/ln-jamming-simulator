from lnmodel import LNModel, FeeType
from channel import dir0, dir1

import pytest

a, b, c, cr, d = "Alice", "Bob", "Charlie", "Craig", "Dave"


@pytest.fixture
def example_snapshot_json():

	# Channel ABx0 has both directions enabled.
	channel_ABx0_right = {
		"source": "Alice",
		"destination": "Bob",
		"short_channel_id": "ABx0",
		"satoshis": 100,
		"active": True
	}
	channel_ABx0_left = {
		"source": "Bob",
		"destination": "Alice",
		"short_channel_id": "ABx0",
		"satoshis": 100,
		"active": True
	}

	# Channel BCx0 has both directions enabled.
	channel_BCx0_right = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx0",
		"satoshis": 100,
		"active": True
	}
	channel_BCx0_left = {
		"source": "Charlie",
		"destination": "Bob",
		"short_channel_id": "BCx0",
		"satoshis": 100,
		"active": True
	}

	# Channel BCx1 has both directions enabled.
	channel_BCx1_right = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx1",
		"satoshis": 50,
		"active": True
	}
	channel_BCx1_left = {
		"source": "Charlie",
		"destination": "Bob",
		"short_channel_id": "BCx1",
		"satoshis": 50,
		"active": True
	}

	# Channel BCx2 has only one ("left") direction _announced_.
	# The other direction will be set to None.
	channel_BCx2_left = {
		"source": "Charlie",
		"destination": "Bob",
		"short_channel_id": "BCx2",
		"satoshis": 500,
		"active": True
	}

	# Channel CDx0 has both directions announced,
	# but only Charlie -> Dave is enabled.
	channel_CDx0_right = {
		"source": "Charlie",
		"destination": "Dave",
		"short_channel_id": "CDx0",
		"satoshis": 100,
		"active": True
	}
	channel_CDx0_left = {
		"source": "Dave",
		"destination": "Charlie",
		"short_channel_id": "CDx0",
		"satoshis": 100,
		"active": False
	}

	# Channel BCrx0 has one direction announced.
	channel_BCrx0_right = {
		"source": "Bob",
		"destination": "Craig",
		"short_channel_id": "BCrx0",
		"satoshis": 30,
		"active": True
	}

	# Channel CrDx0 has one direction announced.
	channel_CrDx0_right = {
		"source": "Craig",
		"destination": "Dave",
		"short_channel_id": "CrDx0",
		"satoshis": 30,
		"active": True
	}

	channels = [
		channel_ABx0_right,
		channel_ABx0_left,
		channel_BCx0_right,
		channel_BCx0_left,
		channel_BCx1_right,
		channel_BCx1_left,
		channel_BCx2_left,
		channel_CDx0_right,
		channel_CDx0_left,
		channel_BCrx0_right,
		channel_CrDx0_right
	]
	graph_json_object = {"channels": channels}
	return graph_json_object


@pytest.fixture
def example_amounts():
	amounts = {
		"small": 10,
		"medium": 80,
		"big": 200,
		"huge": 1000
	}
	return amounts


def test_get_channel_graph_from_json(example_snapshot_json):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	g = ln_model.channel_graph
	assert(all(n in g.nodes() for n in [a, b, c, d, cr]))

	# Alice - Bob has one bi-directional channel
	assert(a in g.neighbors(b))
	ab_edge_data = g.get_edge_data(a, b)
	assert(len(ab_edge_data) == 1 and "ABx0" in ab_edge_data)
	for dirX in [dir0, dir1]:
		assert(ab_edge_data["ABx0"]["directions"][dirX] is not None)
		assert(ab_edge_data["ABx0"]["directions"][dirX].is_enabled)

	# Bob - Charlie have three channels, one of them uni-directional
	assert(b in g.neighbors(c))
	bc_edge_data = g.get_edge_data(b, c)
	assert(
		len(bc_edge_data) == 3
		and "BCx0" in bc_edge_data
		and "BCx1" in bc_edge_data
		and "BCx2" in bc_edge_data
	)
	for dirX in [dir0, dir1]:
		assert(bc_edge_data["BCx0"]["directions"][dirX] is not None)
		assert(bc_edge_data["BCx0"]["directions"][dirX].is_enabled)
		assert(bc_edge_data["BCx1"]["directions"][dirX] is not None)
		assert(bc_edge_data["BCx1"]["directions"][dirX].is_enabled)
	assert(bc_edge_data["BCx2"]["directions"][dir1] is not None)
	assert(bc_edge_data["BCx2"]["directions"][dir1].is_enabled)
	assert(bc_edge_data["BCx2"]["directions"][dir0] is None)

	# Charlie - Dave have a bi-directional channel
	# but direction Dave->Charlie is disabled
	assert(c in g.neighbors(d))
	cd_edge_data = g.get_edge_data(c, d)
	assert(len(cd_edge_data) == 1 and "CDx0" in cd_edge_data)
	assert(cd_edge_data["CDx0"]["directions"][dir0] is not None)
	assert(cd_edge_data["CDx0"]["directions"][dir0].is_enabled)
	# UPD: we don't consider disabled channels
	assert(cd_edge_data["CDx0"]["directions"][dir1] is None)
	#assert(not cd_edge_data["CDx0"]["directions"][dir1].is_enabled)

	# We also have uni-dir channels Bob->Craig->Dave
	# (to test alternative routes)
	for x, y in ((b, cr), (cr, d)):
		assert(x in g.neighbors(y))
		xy_edge_data = g.get_edge_data(x, y)
		assert(len(xy_edge_data) == 1)
		xy_cid = list(xy_edge_data)[0]
		assert(xy_edge_data[xy_cid]["directions"][dir0] is not None)
		assert(xy_edge_data[xy_cid]["directions"][dir0].is_enabled)
		assert(xy_edge_data[xy_cid]["directions"][dir1] is None)


def test_get_routing_graph_from_json(example_snapshot_json):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	g = ln_model.routing_graph
	assert(all(n in g.nodes() for n in [a, b, c, d, cr]))

	# Alice - Bob
	assert(a in g.predecessors(b))
	ab_edge_data = g.get_edge_data(a, b)
	assert(len(ab_edge_data) == 1 and "ABx0" in ab_edge_data)

	# Bob - Alice
	assert(b in g.predecessors(a))
	ba_edge_data = g.get_edge_data(b, a)
	assert(len(ba_edge_data) == 1 and "ABx0" in ba_edge_data)

	# Bob - Charlie
	assert(b in g.predecessors(c))
	bc_edge_data = g.get_edge_data(b, c)
	assert(
		len(bc_edge_data) == 2
		and "BCx0" in bc_edge_data
		and "BCx1" in bc_edge_data
	)

	# Charlie - Bob
	assert(c in g.predecessors(b))
	cb_edge_data = g.get_edge_data(c, b)
	assert(
		len(cb_edge_data) == 3
		and "BCx0" in cb_edge_data
		and "BCx1" in cb_edge_data
		and "BCx2" in cb_edge_data
	)

	# Charlie - Dave have a bi-directional channel
	# but direction Dave->Charlie is disabled
	assert(c in g.predecessors(d))
	cd_edge_data = g.get_edge_data(c, d)
	assert(len(cd_edge_data) == 1 and "CDx0" in cd_edge_data)

	# we only parse active (enabled) channel directions into routing graph
	# that's why we don't have Dave -> Charlie edge
	assert(d not in g.predecessors(c))

	# Bob->Craig->Dave (uni-directional)
	for x, y in ((b, cr), (cr, d)):
		assert(x in g.predecessors(y))
		xy_edge_data = g.get_edge_data(x, y)
		assert(len(xy_edge_data) == 1)


def test_revenue(example_snapshot_json):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	# all revenues must be zero initially
	for n in ln_model.channel_graph.nodes():
		assert(ln_model.get_revenue(n, FeeType.UPFRONT) == 0)
		assert(ln_model.get_revenue(n, FeeType.SUCCESS) == 0)
	assert("Alice" in ln_model.channel_graph.nodes())
	# add 10 to Alice's success revenue, it should become 10
	# also make sure that changes in one revenue type don't affect the other
	ln_model.add_revenue("Alice", FeeType.SUCCESS, 10)
	assert(ln_model.get_revenue("Alice", FeeType.SUCCESS) == 10)
	assert(ln_model.get_revenue("Alice", FeeType.UPFRONT) == 0)
	# subtract 20 from Alice's upfront revenue, it should become -20
	ln_model.subtract_revenue("Alice", FeeType.UPFRONT, 20)
	assert(ln_model.get_revenue("Alice", FeeType.SUCCESS) == 10)
	assert(ln_model.get_revenue("Alice", FeeType.UPFRONT) == -20)


def test_get_routing_graph_for_amount(example_snapshot_json, example_amounts):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	ln_g_filtered = ln_model.get_routing_graph_for_amount(example_amounts["medium"])
	must_contain_cids = ["ABx0", "BCx0", "BCx2", "CDx0"]
	must_not_contain_cids = ["BCx1", "BCrx0", "CrDx0"]
	cids = [value[2] for value in ln_g_filtered.edges(keys=True)]
	for cid in must_contain_cids:
		assert(cid in cids)
	for cid in must_not_contain_cids:
		assert(cid not in cids)
	# now filter for a huge amount - will exclude everything
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	ln_g_filtered = ln_model.get_routing_graph_for_amount(example_amounts["huge"])
	must_not_contain_cids = ["ABx0", "BCx0", "BCx2", "CDx0", "BCx1", "BCrx0", "CrDx0"]
	cids = [value[2] for value in ln_g_filtered.edges(keys=True)]
	for cid in must_not_contain_cids:
		assert(cid not in cids)


def test_get_routes(example_snapshot_json, example_amounts):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	# get routes from Alice to Dave for moderate amount
	# there should be two: via Bob-Charlie and Bob-Craig
	routes = ln_model.get_shortest_routes(a, d, example_amounts["small"])
	routes_list = [p for p in routes]
	print(routes_list)
	assert(len(routes_list) == 2)
	assert([a, b, c, d] in routes_list)
	assert([a, b, cr, d] in routes_list)
	# get routes for a medium amount: there should be only one
	routes = ln_model.get_shortest_routes(a, d, example_amounts["medium"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)
	assert([a, b, c, d] in routes_list)
	# get routes for amount that is too big
	routes = ln_model.get_shortest_routes(a, d, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)

'''
def test_get_routes_via_nodes(example_ln_model, example_amounts):
	# generate all routes from Alice to Dave
	# through the Bob-Charlie hop specifically
	# (Craig should not be used)
	routes = example_ln_model.get_shortest_routes_via_nodes(a, d, example_amounts["medium"], [b, c])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)
	assert([a, b, c, d] in routes_list)
'''


# test directionality: there must not be a route B <--- C for a big amount
def test_directionality(example_snapshot_json, example_amounts):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	# B-C could forward a big amount in the opposite direction ("left")
	routes = ln_model.get_shortest_routes(b, c, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)
	# but there is a route in the "left" direction
	routes = ln_model.get_shortest_routes(c, b, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)


# test disabled direction: there must not be a route C <--- D
def test_disabled_channel_direction(example_snapshot_json, example_amounts):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	# check that disabled direction doesn't work
	routes = ln_model.get_shortest_routes(d, c, example_amounts["small"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)


def test_set_fee(example_snapshot_json):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	amount = 100
	ch_dir = ln_model.channel_graph.get_edge_data(a, b)["ABx0"]["directions"][a < b]
	assert(ch_dir.success_fee_function(amount) == 0)
	ln_model.set_fee(a, b, FeeType.SUCCESS, 1, 0.02)
	assert(ch_dir.success_fee_function(amount) == 3)


def test_get_shortest_routes_wrong_nodes(example_snapshot_json):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	routes = ln_model.get_shortest_routes("Alice", "Zoe", 100)
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)


def test_get_suitable_cid_ch_dirs_in_hop(example_snapshot_json):
	ln_model = LNModel(
		example_snapshot_json,
		default_num_slots=2,
		no_balance_failures=True)
	cid_ch_dirs = ln_model.get_suitable_cid_ch_dirs_in_hop("Bob", "Charlie", 0)
	assert(cid_ch_dirs)

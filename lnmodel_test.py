from lnmodel import LNModel, RevenueType, get_channel_graph_from_json, get_routing_graph_from_json
from channel import dir0, dir1

import pytest

a, b, c, cr, d = "Alice", "Bob", "Charlie", "Craig", "Dave"
DEFAULT_NUM_SLOTS = 2


@pytest.fixture
def example_snapshot_json():

	# Channel ABx0 has both directions enabled.
	channel_ABx0_right = {
		"source": "Alice",
		"destination": "Bob",
		"short_channel_id": "ABx0",
		"satoshis": 100,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}
	channel_ABx0_left = {
		"source": "Bob",
		"destination": "Alice",
		"short_channel_id": "ABx0",
		"satoshis": 100,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}

	# Channel BCx0 has both directions enabled.
	channel_BCx0_right = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx0",
		"satoshis": 100,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}
	channel_BCx0_left = {
		"source": "Charlie",
		"destination": "Bob",
		"short_channel_id": "BCx0",
		"satoshis": 100,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}

	# Channel BCx1 has both directions enabled.
	channel_BCx1_right = {
		"source": "Bob",
		"destination": "Charlie",
		"short_channel_id": "BCx1",
		"satoshis": 50,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}
	channel_BCx1_left = {
		"source": "Charlie",
		"destination": "Bob",
		"short_channel_id": "BCx1",
		"satoshis": 50,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}

	# Channel BCx2 has only one ("left") direction _announced_.
	# The other direction will be set to None.
	channel_BCx2_left = {
		"source": "Charlie",
		"destination": "Bob",
		"short_channel_id": "BCx2",
		"satoshis": 500,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}

	# Channel CDx0 has both directions announced,
	# but only Charlie -> Dave is enabled.
	channel_CDx0_right = {
		"source": "Charlie",
		"destination": "Dave",
		"short_channel_id": "CDx0",
		"satoshis": 100,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}
	channel_CDx0_left = {
		"source": "Dave",
		"destination": "Charlie",
		"short_channel_id": "CDx0",
		"satoshis": 100,
		"active": False,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}

	# Channel BCrx0 has one direction announced.
	channel_BCrx0_right = {
		"source": "Bob",
		"destination": "Craig",
		"short_channel_id": "BCrx0",
		"satoshis": 30,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
	}

	# Channel CrDx0 has one direction announced.
	channel_CrDx0_right = {
		"source": "Craig",
		"destination": "Dave",
		"short_channel_id": "CrDx0",
		"satoshis": 30,
		"active": True,
		"base_fee_millisatoshi": 0,
		"fee_per_millionth": 0,
		"base_fee_millisatoshi_upfront": 0,
		"fee_per_millionth_upfront": 0
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
def example_ln_model(example_snapshot_json):
	return LNModel(example_snapshot_json, DEFAULT_NUM_SLOTS)


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
	g = get_channel_graph_from_json(example_snapshot_json, DEFAULT_NUM_SLOTS)
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
	assert(cd_edge_data["CDx0"]["directions"][dir1] is not None)
	assert(not cd_edge_data["CDx0"]["directions"][dir1].is_enabled)

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
	g = get_routing_graph_from_json(example_snapshot_json)
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


def test_revenue(example_ln_model):
	# all revenues must be zero initially
	for n in example_ln_model.channel_graph.nodes():
		assert(example_ln_model.get_revenue(n, RevenueType.UPFRONT) == 0)
		assert(example_ln_model.get_revenue(n, RevenueType.SUCCESS) == 0)
	assert("Alice" in example_ln_model.channel_graph.nodes())
	# add 10 to Alice's success revenue, it should become 10
	# also make sure that changes in one revenue type don't affect the other
	example_ln_model.add_revenue("Alice", RevenueType.SUCCESS, 10)
	assert(example_ln_model.get_revenue("Alice", RevenueType.SUCCESS) == 10)
	assert(example_ln_model.get_revenue("Alice", RevenueType.UPFRONT) == 0)
	# subtract 20 from Alice's upfront revenue, it should become -20
	example_ln_model.subtract_revenue("Alice", RevenueType.UPFRONT, 20)
	assert(example_ln_model.get_revenue("Alice", RevenueType.SUCCESS) == 10)
	assert(example_ln_model.get_revenue("Alice", RevenueType.UPFRONT) == -20)


def test_get_routing_graph_for_amount(example_ln_model, example_amounts):
	ln_g_filtered = example_ln_model.get_routing_graph_for_amount(example_amounts["medium"])
	must_contain_cids = ["ABx0", "BCx0", "BCx2", "CDx0"]
	must_not_contain_cids = ["BCx1", "BCrx0", "CrDx0"]
	cids = [value[2] for value in ln_g_filtered.edges(keys=True)]
	for cid in must_contain_cids:
		assert(cid in cids)
	for cid in must_not_contain_cids:
		assert(cid not in cids)
	# now filter for a huge amount - will exclude everything
	ln_g_filtered = example_ln_model.get_routing_graph_for_amount(example_amounts["huge"])
	must_contain_cids = []
	must_not_contain_cids = ["ABx0", "BCx0", "BCx2", "CDx0", "BCx1", "BCrx0", "CrDx0"]
	cids = [value[2] for value in ln_g_filtered.edges(keys=True)]
	for cid in must_contain_cids:
		assert(cid in cids)
	for cid in must_not_contain_cids:
		assert(cid not in cids)


def test_get_routes(example_ln_model, example_amounts):
	# get routes from Alice to Dave for moderate amount
	# there should be two: via Bob-Charlie and Bob-Craig
	routes = example_ln_model.get_routes(a, d, example_amounts["small"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 2)
	assert([a, b, c, d] in routes_list)
	assert([a, b, cr, d] in routes_list)
	# get routes for a medium amount: there should be only one
	routes = example_ln_model.get_routes(a, d, example_amounts["medium"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)
	assert([a, b, c, d] in routes_list)
	# get routes for amount that is too big
	routes = example_ln_model.get_routes(a, d, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)


def test_get_routes_via_hop(example_ln_model, example_amounts):
	# generate all routes from Alice to Dave
	# through the Bob-Charlie hop specifically
	# (Craig should not be used)
	routes = example_ln_model.get_routes_via_hop(a, b, c, d, example_amounts["medium"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)
	assert([a, b, c, d] in routes_list)


# test directionality: there must not be a route B <--- C for a big amount
def test_directionality(example_ln_model, example_amounts):
	# B-C could forward a big amount in the opposite direction ("left")
	routes = example_ln_model.get_routes(b, c, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)
	# but there is a route in the "left" direction
	routes = example_ln_model.get_routes(c, b, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)


# test disabled direction: there must not be a route C <--- D
def test_disabled_channel_direction(example_ln_model, example_amounts):
	# check that disabled direction doesn't work
	routes = example_ln_model.get_routes(d, c, example_amounts["small"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)


def test_set_fee_function(example_ln_model):
	amount = 100
	ch_dir = example_ln_model.channel_graph.get_edge_data(a, b)["ABx0"]["directions"][a < b]
	assert(ch_dir.success_fee_function(amount) == 0)
	example_ln_model.set_fee_function(a, b, RevenueType.SUCCESS, 1, 0.02)
	assert(ch_dir.success_fee_function(amount) == 3)

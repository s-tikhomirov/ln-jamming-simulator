from lnmodel import LNModel, FeeType, ErrorType
from channel import dir0, dir1
from payment import Payment

import pytest

a, b, c, cr, d = "Alice", "Bob", "Charlie", "Craig", "Dave"


def get_example_snapshot_json():

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


def get_ln_model():
	return LNModel(
		get_example_snapshot_json(),
		default_num_slots=2,
		no_balance_failures=True)


@pytest.fixture
def example_amounts():
	amounts = {
		"small": 10,
		"medium": 80,
		"big": 200,
		"huge": 1000
	}
	return amounts


def test_get_channel_graph_from_json():
	ln_model = get_ln_model()
	g = ln_model.channel_graph
	assert(all(n in g.nodes() for n in [a, b, c, d, cr]))

	# Alice - Bob has one bi-directional channel
	assert(g.has_edge(a, b))
	ab_hop = ln_model.get_hop(a, b)
	assert(ab_hop.get_num_cids() == 1 and ab_hop.has_cid("ABx0"))
	assert(ab_hop.get_channel("ABx0").is_enabled_in_both_directions())

	# Bob - Charlie have three channels, one of them uni-directional
	assert(g.has_edge(b, c))
	bc_hop = ln_model.get_hop(b, c)
	assert(bc_hop.get_num_cids() == 3)
	assert(bc_hop.has_cid("BCx0"))
	assert(bc_hop.has_cid("BCx1"))
	assert(bc_hop.has_cid("BCx2"))
	assert(bc_hop.get_channel("BCx0").is_enabled_in_both_directions())
	assert(bc_hop.get_channel("BCx1").is_enabled_in_both_directions())
	assert(bc_hop.get_channel("BCx2").is_enabled_in_direction(dir1))
	assert(not bc_hop.get_channel("BCx2").is_enabled_in_direction(dir0))

	# Charlie - Dave have a bi-directional channel
	# but direction Dave->Charlie is disabled
	assert(g.has_edge(c, d))
	cd_hop = ln_model.get_hop(c, d)
	assert(cd_hop.get_num_cids() == 1 and cd_hop.has_cid("CDx0"))
	assert(cd_hop.get_channel("CDx0").is_enabled_in_direction(dir0))
	assert(not cd_hop.get_channel("CDx0").is_enabled_in_direction(dir1))

	# We also have uni-dir channels Bob->Craig->Dave
	# (to test alternative routes)
	for x, y in ((b, cr), (cr, d)):
		assert(g.has_edge(x, y))
		xy_hop = ln_model.get_hop(x, y)
		assert(xy_hop.get_num_cids() == 1)
		xy_cid = xy_hop.get_cids()[0]
		xy_ch = xy_hop.get_channel(xy_cid)
		assert(xy_ch.is_enabled_in_direction(dir0))
		assert(not xy_ch.is_enabled_in_direction(dir1))


def test_get_routing_graph_from_json():
	ln_model = get_ln_model()
	g = ln_model.routing_graph
	assert(all(n in g.nodes() for n in [a, b, c, d, cr]))

	# Alice - Bob
	assert(g.has_edge(a, b))
	ab_edge = ln_model.get_routing_graph_edge_data(a, b)
	assert(len(ab_edge) == 1 and "ABx0" in ab_edge)

	# Bob - Alice
	assert(g.has_edge(b, a))
	ba_edge = ln_model.get_routing_graph_edge_data(b, a)
	assert(len(ba_edge) == 1 and "ABx0" in ba_edge)

	# Bob - Charlie
	assert(g.has_edge(b, c))
	bc_edge = ln_model.get_routing_graph_edge_data(b, c)
	assert(len(bc_edge) == 2)
	assert("BCx0" in bc_edge)
	assert("BCx1" in bc_edge)

	# Charlie - Bob
	assert(g.has_edge(c, b))
	cb_edge = ln_model.get_routing_graph_edge_data(c, b)
	assert(len(cb_edge) == 3)
	assert("BCx0" in cb_edge)
	assert("BCx1" in cb_edge)
	assert("BCx2" in cb_edge)

	# Charlie - Dave have a bi-directional channel
	# but direction Dave->Charlie is disabled
	assert(g.has_edge(c, d))
	cd_edge = ln_model.get_routing_graph_edge_data(c, d)
	assert(len(cd_edge) == 1 and "CDx0" in cd_edge)

	# we only parse active (enabled) channel directions into routing graph
	# that's why we don't have Dave -> Charlie edge
	assert(not g.has_edge(d, c))

	# Bob->Craig->Dave (uni-directional)
	for x, y in ((b, cr), (cr, d)):
		assert(g.has_edge(x, y))
		xy_edge = ln_model.get_routing_graph_edge_data(x, y)
		assert(len(xy_edge) == 1)


def test_revenue():
	ln_model = get_ln_model()
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


def test_get_routing_graph_for_amount(example_amounts):
	ln_model = get_ln_model()
	ln_g_filtered = ln_model.get_routing_graph_for_amount(example_amounts["medium"])
	must_contain_cids = ["ABx0", "BCx0", "BCx2", "CDx0"]
	must_not_contain_cids = ["BCx1", "BCrx0", "CrDx0"]
	cids = [value[2] for value in ln_g_filtered.edges(keys=True)]
	for cid in must_contain_cids:
		assert(cid in cids)
	for cid in must_not_contain_cids:
		assert(cid not in cids)
	# now filter for a huge amount - will exclude everything
	ln_model = get_ln_model()
	ln_g_filtered = ln_model.get_routing_graph_for_amount(example_amounts["huge"])
	must_not_contain_cids = ["ABx0", "BCx0", "BCx2", "CDx0", "BCx1", "BCrx0", "CrDx0"]
	cids = [value[2] for value in ln_g_filtered.edges(keys=True)]
	for cid in must_not_contain_cids:
		assert(cid not in cids)


def test_get_routes(example_amounts):
	ln_model = get_ln_model()
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


# test directionality: there must not be a route B <--- C for a big amount
def test_directionality(example_amounts):
	ln_model = get_ln_model()
	# B-C could forward a big amount in the opposite direction ("left")
	routes = ln_model.get_shortest_routes(b, c, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)
	# but there is a route in the "left" direction
	routes = ln_model.get_shortest_routes(c, b, example_amounts["big"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 1)


# test disabled direction: there must not be a route C <--- D
def test_disabled_channel_direction(example_amounts):
	ln_model = get_ln_model()
	# check that disabled direction doesn't work
	routes = ln_model.get_shortest_routes(d, c, example_amounts["small"])
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)


def test_set_fee_for_all():
	ln_model = get_ln_model()
	ab_hop = ln_model.get_hop(a, b)
	ch = ab_hop.get_channel("ABx0")
	ch_dir = ch.get_chdir(direction=(a < b))
	amount = 100
	assert(ch_dir.success_fee_function(amount) == 0)
	ln_model.set_fee_for_all(FeeType.SUCCESS, base=1, rate=0.02)
	assert(ch_dir.success_fee_function(amount) == 3)
	ln_model.set_upfront_fee_from_coeff_for_all(upfront_base_coeff=2, upfront_rate_coeff=3)
	assert(ch_dir.upfront_fee_function(amount) == 2 + 0.06 * amount)


def test_get_shortest_routes_wrong_nodes():
	ln_model = get_ln_model()
	routes = ln_model.get_shortest_routes("Alice", "Zoe", 100)
	routes_list = [p for p in routes]
	assert(len(routes_list) == 0)


def test_get_cids_can_forward_by_fee():
	ln_model = get_ln_model()
	cids = ln_model.get_cids_can_forward_by_fee("Bob", "Charlie", 1)
	assert(cids)
	cids = ln_model.get_cids_can_forward_by_fee("Bob", "Charlie", 1000)
	assert(not cids)


def test_get_prob_balance_failure():
	ln_model = get_ln_model()
	# capacity of ABx0 is 100
	prob_balance_failure = ln_model.get_prob_balance_failure("Alice", "Bob", "ABx0", 10)
	assert(prob_balance_failure == 0.1)


def test_balance_failure():
	ln_model = LNModel(
		get_example_snapshot_json(),
		default_num_slots=2,
		no_balance_failures=False)
	p_ab = Payment(
		downstream_payment=None,
		downstream_node="Bob",
		upfront_fee_function=lambda a: 0,
		success_fee_function=lambda a: 0,
		desired_result=True,
		processing_delay=1,
		receiver_amount=100)
	reached_receiver, last_node_reached, first_node_not_reached, error_type = ln_model.attempt_send_payment(p_ab, sender="Alice", now=0)
	assert(not reached_receiver)
	assert(last_node_reached == "Alice")
	assert(first_node_not_reached == "Bob")
	assert(error_type == ErrorType.LOW_BALANCE)

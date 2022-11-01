
The code contains the following classes.

## Channel

A `Channel` represents a channel between two Lightning nodes.
Each `Channel` has an identifier (`cid`), a capacity, and two `ChannelDirection`s (one for each `Direction`).
If a channel is disabled in a given direction, the corresponding `ChannelDirection` value is `None`.

## ChannelDirection

A `ChannelDirection` represents a `Channel`'s ability to route payments in a particular `Direction`.
A `ChannelDirection` object scores four fee coefficients, namely, the base fee and the proportional fee rate for success-case and for unconditional fees.
It also contains a priority queue of in-flight `Htlc`s ordered by their absolute resolution time.

## Direction

Each channel can forward payments in up to two directions.
We define `Direction` in the relation to the channel parties' node identifiers: `Direction.Alph` (alphanumerical) and `Direction.NonAlph`.

## Event

An `Event` describes a future simulated `Payment` (which may be an honest payment or a jam).
Among other parameters, it contains the _processing delay_ and the _desired result_.
The processing delay determines the progress of simulated time when a `Schedule` of `Event`s is executed.
The desired result distinguishes honest payments (`desired_result == True`) from jams (`desired_result == False`).

## Hop

A `Hop` represents the set of all `Channel`s between a pair of nodes.
Functions of this class allow for filtering and sorting channels based on arbitrary conditions.
A typical use case here is to select channels with sufficient capacity for a given amount and sort them by fees.

## Htlc

An `Htlc` is an in-flight payment in a particular `ChannelDirection` due for resolution at a specific time.
To resolve an HTLC means to add its amount to one of the node's balances.
If the HTLC is honest and reaches the receiver, its amount is added downstream, otherwise upstream.

During simulation, channels may contain "outdated" HTLCs (i.e., those with resolution time lower than the current simulated time).
Note: honest payments also create HTLCs that don't resolve right away!
For efficiency reasons, HTLCs are resolved lazily.
HTLCs are only resolved in one of two cases:
- Simulation has ended.
- A `Payment` is being forwarded through this `ChannelDirection`, but the HTLC queue is full (i.e., all slots are busy). In that case, we pop the HTLC with the earliest resolution time, and resolve it if it is outdated. If even the earliest HTLC is to be resolved in the future, we fail the payment being forwarded (this means, the channel is fully jammed).

## LNModel

An `LNModel` models the Lightning network.
It is based on a snapshot either from a JSON file or an inline JSON object.
The expected format corresponds to the output of [`listchannels`](https://lightning.readthedocs.io/lightning-listchannels.7.html) API call in [Core Lightning](https://github.com/ElementsProject/lightning).

Internally, `LNModel` contains two NetworkX graphs: the hop graph and the routing graph.
The hop graph is non-directed and doesn't allow parallel edges (NetworkX type `Graph`).
Each edge is associated with a `Hop`, which, in turn, contains `Channel`s, `ChannelDirection`s, and `Htlc`s.
The routing graph is directed and allows parallel edges (NetworkX's `MultiDiGraph`).
Edges in the routing graph only store channel ids and capacities.
The routing graph is used for path-finding, while the hop graph stores the data being updated as `Payment`s are routed.

## Payment

A `Payment` describes a payment to be forwarded through a specified route.
A `Payment` is a recursive data structure: it describes the potential value transfer at the current hop, and contains another `Payment` object describing what happens at the next hop.
Consider an example.
For a route (Alice - Bob - Charlie), the outermost `Payment` describes what Alice pays to Bob.
The next-layer `Payment` instance (`downstream_payment`) describes what Bob pays to Charlie.
At the last hop, the downstream payment is `None`.

A `Payment` is creates based on an `Event` (popped from a `Schedule`) and the fee policies of channels along a chosen route.
Currently, for each hop, the cheapest channel is preferred.

A note on fee calculation: we distinguish between payment _body_ and payment _amount_.
Consider a hop from Alice to Bob.
The payment _body_ is what Alice wants Bob to forward (or keep, if Bob is the final receiver).
The payment _amount_ is comprised of the payment body and the success-case fee (which is zero on the last hop).
Routing nodes only see the _amount_ of each payment they forward, without knowing how that amount is split into the body and the fee.
We calculate the unconditional fee based on the payment amount, whereas the success-case fee is calculated based on the payment body:

```
f_s = success_fee(body)
amount = body + f_s
f_u = unconditional_fee(amount)

```

## Router

A `Router` generates routes for payments that go through a specified list of (target) node pairs.
This functionality is only used for jamming simulations (honest payments can be assumed to take the shortest route).
A `Router`, given a list of target node pairs, constructs a generator of routes, which `yield`s routes one by one.
The router tries to include as many target node pairs in a route as possible, staying within the maximum allowed route length.

## Scenario

A `Scenario` reflects a set of parameters for a given simulation, such as: the snapshot being used, whether channels fail due to lack of balance, who the senders and receivers are, whether honest of jamming routes must pass through specific nodes, and so on.

## Schedule

A `Schedule` stores a priority queue of `Event`s ordered by timestamp.
A schedule is populated as follows.
Until a given end time is exceeded, generate a processing delay, add it to the last event's time, and push a new event `Event` into the schedule.

A schedule separately stores its end time (which may not be the same as the timestamp of its last event).
For example, the last event in a `30`-second schedule may have a timestamp `28.43`.

We define two sub-classes from `Schedule`: `HonestSchedule` and `GenericSchedule` that only contain "honest" and "jamming" events, respectively.
An honest event has randomized amount and delay, and its desired result is `True`.
A jamming event has fixed value (the dust limit) and delay, and its desired results is `False`.
A generic `Schedule` can be populated with a mix of honest and jamming events, but for our simulations we only use `HonestSchedule` and `JammingSchedule`.


## Simulator

A `Simulator` runs a series of simulations and returns the averaged results across a given number or runs.
`HonestSimulator` and `JammingSimulator` inherit a generic `Simulator` class and implement, respectively, the honest and the jamming simulations.

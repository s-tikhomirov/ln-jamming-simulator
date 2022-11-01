This file contains a more elaborate description of the internal workings of a simulation.

## General simulation structure

Both simulation types (honest and jamming) share a fundamental structure but differ in details.
The common structure is:

1. construct a Schedule;
2. execute the Schedule;
3. collect the results.

A Schedule is a priority queue of Events.
An Event encodes a payment to be simulated and includes these fields: sender, receiver, amount, desired result, and processing delay.

Given a schedule, the simulator:

1. picks the next event from the Schedule;
2. constructs a route from the sender to the receiver that is able to forward the required amount;
3. creates a Payment object that models a payment due to be forwarded through a particular route (that is, it is wrapped w.r.t specific fee policies of channels along the chosen route);
4. sends the payment along the route and receives the result.

If the payment doesn't reach the receiver, it has no effect on the slots in channels (payments fail instantly).
If the payment reaches the receiver, its in-flight HTLCs are stored in the slots of the channels along the route.
Each in-flight HTLC encodes the effects it would have when resolved, and its resolution time (current time + payment delay).
For honest payment, delays are generated randomly.
For jams, delays are constant.

An in-flight HTLC contains the resolution time (now + delay), the desired result, and the amount.
We don't model balances, therefore the HTLC amount only reflects success-case fees.
On HTLC resolution, the fee moves "forward" if the desired result was True, and "backward" otherwise.

We resolve HTLCs lazily.
This means that at each routing step, we first check whether the next hop has a free slot.
If it does, we continue forwarding.
If it does not (all slots are full), we check the timestamp of the _earliest_ in-flight HTLC is.
(The priority queue makes it easy to query the element with the lowest resolution timestamp.)
If the timestamp of the earliest HTLC is in the past (i.e., it should already have been resolved), we pop it from the queue and apply, freeing up a slot for the payment we currently route.
If no such HTLC can be resolves, the channel is considered jammed, and the current payment is failed.

Note that _during_ simulation channels do store outdated HTLCs.
This is not a problem as long as we free up slots just-in-time, as described above.
At the end of the simulation, we additionally iterate through all channels and resolve all outdated HTLCs to calculate everyone's final revenue.

## Honest simulation details

In an honest simulation, events in the schedule model honest payments (their desired results is `True`).
As soon as an honest payment reaches the receiver, the simulator moves on to the next event.
For honest payments, we prefer shortest routes (not weighted by fees or other metrics).
Each route may be tried multiple times to overcome potential balance errors.
If a route has been tried the maximum number of times but all attempts have failed, we move to the next suggested route, and so on, until either of the following happens:

- the payment reaches the receiver;
- no more routes exist;
- the maximum number of routes is exceeded.

Optionally, a payment may specify that it must be routed through specific nodes (i.e., through the node labeled as a hub).

## Jamming simulation details

Jamming simulation differs from honest payment simulation in two ways.
First, in jamming, we move to the next event when all target node pairs are jammed.
In contrast, an honest payment is considered "done" as soon as it reaches the receiver.
Second, in jamming, we pick routes to include as many target node pairs as possible, and not the shortest route.

Jamming proceeds in batches.
All jams incur the same delay along the route, if they reach the (jammer-)receiver.
As long as the jamming continues until everything the attacker wants jammed is indeed jammed, a jamming event corresponds to what we call a _batch_ of jams.
Let's say the jam delay is 7 seconds.
At time 0, we send a batch of jams that blocks all target channels.
Then, we wait until time 7, and send another jam batch, and so on.
Each batch may contain slightly different number of jams, as some jams may randomly fail.
Moreover, a batch may be finished prematurely, if no unjammed routes exist to some target channels.

From an implementation perspective, in a jamming schedule, each event corresponds to a jam batch.
A jamming simulation starts with just one event scheduled for time 0.
When the batch is complete, the simulator _pushes_ a new event into the schedule for the next batch time (7 seconds).
The process continues until the simulation time runs out.
This behavior is in contrast to honest simulation, where no new events are pushed into the schedule while it is being processed.

Route construction in jamming simulation also differs from the honest scenario.
The attacker aims to jam as many yet unjammed target channels as possible with a single route.
To construct routes, we iterate through subsets of target node pairs and try building routes that touch all of them.
We start from larger subsets and move on to smaller ones as simulation proceeds.

In more detail: we first pick a subset of yet unjammed target node pairs.
We then pick a permutation of hops in this subset.
Given a fixed permutation (a list of node pairs), we try to construct a route that includes them _in this order_.
This works as follows:
1. find a route from the sender to the first node pair in the list;
2. find a route from the end of the first node pair to the beginning of the second node pair;
3. ...and so on, until either the list is depleted, or there are no sub-routes.

Routes may be circular.
Consider a hub-based topology, where Alice and Bob are connected to a Hub.
A target node pair permutation may be: (Alice, Hub), (Hub, Alice), (Bob, Hub), (Hub, Bob).
Imagine that the sender has a channel to Alice.
We construct the route as follows:
1. Sender - Alice
2. Sender - Alice - Hub
3. Sender - Alice - Hub - Alice
4. (searching for a sub-route from Alice to Bob, found sub-route Alice - Hub - Bob): Sender - Alice - Hub - Alice - Hub - Bob

Even though the number of all permutations of all subsets of target node pairs is huge, we don't need to traverse them all.
In fact, we only need to traverse about as many routes as there are target node pairs.
After jamming each route, we exclude one target node pair from the list of unjammed hops.
(Other hops along the route may be jammed at this point too, if they all share the same number of slots, but we can't be sure without getting an error message from them.)
Therefore, the number of path-finding operations is roughly proportional to the number of target node pairs (think a few thousand for the most-connected node).

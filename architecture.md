A summary of the architecture of this simulator.

Launch with `run.py`. Some arguments that may be specified:
- whether to use one of the small testing graphs, of the full real graph
- target node: if provided, the jammer aims to jam all its adjacent nodes
- target hops: an alternative way to specify target hops is to list them explicitly
- honest senders and honest receivers: honest payment flow will be generated from a random sender node to a random receiver node (both picked uniformly for now)
- which nodes the jammer MUST send jams through - used in the experiment with jamming through a fixed route
- which nodes the jammer connects to (for sending jams from and for receiving jams to). By default, the jammer connects to all endpoints of all target hops.
- which nodes honest senders MUST send jams through - used in the "wheel" topology experiment to model the payment flow through the hub specifically.
- the maximum number of target hops per route (explained below in the routing section).

# Preparatory steps

This is what we do before the actual simulation:
- parse a given graph (either from a JSON file or from an inline JSON object)
- assign the default success-case fee and the number of slots to each channel
- set target hops (explicitly given or all adjacent to the target node)
- set honest senders and receivers
- opens jammer's channels (to explicitly given entry nodes or to all target hops' endpoints)

To model the worst-case scenario, we assign a very high number of slots to the attacker's channels.
Namely, each attacker's channel gets (483+1) slots per each target hop.
This way we make sure that the lack of slots is not the limiting factor for the attack.
We may think of such oversized channels are multiple channels under the hood.

# Simulations

We then run two simulation series: honest payments, and jamming.
Each series considers a pair of upfront fee coefficients, picked from given ranges.
For example, the base coefficient may be `0.001`, and the rate coefficient may be `0.1`.
This means that the upfront base fee would be `0.001` of the respective channel's success-case fee; same with the fee rate.

Given a pair of coefficients, we run a simulation a few times (also provided in the CLI arguments).
The results (i.e., nodes' revenues) are averaged across the runs.
The results are accumulated in a JSON object such as:

```
{
    "params": {
        "scenario": "wheel",
        "num_target_hops": 8,
        "duration": 30,
        "num_runs_per_simulation": 10,
        "success_base_fee": 1,
        "success_fee_rate": 5e-06,
        "no_balance_failures": false,
        "default_num_slots_per_channel_in_direction": 483,
        "max_num_attempts_per_route_honest": 10,
        "max_num_attempts_per_route_jamming": 493,
        "dust_limit": 354,
        "honest_payment_every_seconds": 10,
        "min_processing_delay": 1,
        "expected_extra_processing_delay": 3,
        "jam_delay": 7
    },
    "simulations": {
        "honest": [
            {
                "upfront_base_coeff": 0,
                "upfront_rate_coeff": 0,
                "stats": {
                    "num_sent": 3.2,
                    "num_failed": 0.4,
                    "num_reached_receiver": 2.8
                },
                "revenues": {
                    "Alice": -1.3611165,
                    "Hub": 3.0027425,
                    "Bob": -0.5166645,
                    "Charlie": -0.3822195,
                    "Dave": -0.742742,
                    "JammerSender": 0,
                    "JammerReceiver": 0
                }
            }
        ],
        "jamming": [
            {
                "upfront_base_coeff": 0,
                "upfront_rate_coeff": 0,
                "stats": {
                    "num_sent": 2471.9,
                    "num_failed": 2471.9,
                    "num_reached_receiver": 2425
                },
                "revenues": {
                    "Alice": 0.0,
                    "Hub": 0.0,
                    "Bob": 0.0,
                    "Charlie": 0.0,
                    "Dave": 0.0,
                    "JammerSender": 0.0,
                    "JammerReceiver": 0.0
                }
            }
        ]
    }
}
```

The results are saved into two files: a JSON file (dumped as is) and a CSV file, suitable for pasting into a spreadsheet.
The CSV file contains first the results of the honest simulations (in a table form), then the jamming results, then the experiment parameters for reference.

## General simulation structure

Both simulation types (honest and jamming) share a fundamental structure but differ in details.
The common structure is:

1. construct a Schedule
2. execute the Schedule
3. collect the results

A Schedule is a priority queue of Events.
An Event encode a payment to be made.
It includes these fields: sender, receiver, amount, desired results, and processing delay.

Given a schedule, the simulator:

1. picks the next event from the Schedule;
2. constructs a route from the sender to the receiver that is able to forward the required amount;
3. creates a Payment object that models a payment due to be forwarded through a particular route (that is, it is wrapped w.r.t specific fee policies of channels along the chosen route);
4. send the payment along the route and receive the result.

If the payment doesn't reach the receiver, it has no effect on the slots in channels.
(We assume that failed payments fail instantly.)
If the payment does reach the receiver, the respective in-flight HTLCs are being created and stored in the slots of the channels along the route.
An in-flight HTLC encodes the effects it would have when resolved, and the resolution time (current time + delay).

For honest payment, delays are randomly generated.
For jams, delays are constant.
An in-flight HTLC contains the resolution time (now + delay), the desired result, and the amount.
As we don't model balances, the amount only reflects success-case fees to be paid if the payment completes.
Upon HTLC resolution, the fee moves "forward" if the desired result was True, and "backward" otherwise.

We resolve HTLCs lazily.
This means that at each routing iteration, the simulator checks whether the next hop has a free slot.
Only if the queue is full, it check what the timestamp of the earliest in-flight HTLC is.
If it is in the past (i.e., the HTLC should have been resolved), it is popped from the queue and applied.

At the end of the simulation, we go through the whole graph and resolve all (outdated) in-flight HTLCs.

## Honest simulation details

In an honest simulation, events in the schedule model honest payments -- their desired results is True.
As soon as an honest payment reaches the receiver, the simulator moves on to the next event.
The simulator prefers shortest routes (not weighted by fees or other metrics).
Each route may be tried multiple times to overcome potential balance errors.
If a route has been tried the maximum number of times but all attempts have failed, we move to the next route, and so on, until either of the following happens:

- the payment reaches the receiver
- there are no more routes
- the maximum number of routes is exceeded

An event may specify that it must be routed through specific nodes - the route builder accounts for that.

## Jamming simulation details

Jamming simulation differs from honest payment simulation in two ways.
First, the criteria to move to the next event.
In jamming, we move to the next event when all target hops are jammed (as opposed to payment reaching the receiver once).
Second, the jammer cares which route the jam goes through, whereas honest senders can use any route that gets the payment to the receiver.

In our model, jamming works in batches.
All jams incur the same processing delay along the route, if they reach the (jammer-)receiver.
Each event corresponds to a _batch_ of jams.
We define batch as jams that are being send at the same time.
Say, the jam delay is 7.
We start the simulation at time 0 by sending a _batch_ of payments over multiple routes.
We use each routes multiple times, until all target hops are jammed.
When all target hops are jammed, or when no more hops can be jammed (i.e., there are no more routes), the jammer finishes the batch and pushes another event into the schedule.
This new event has all the same properties except for its execution time, which is 7 instead of 0.
Repeating the cycle, the jammer pushes the event due at time 7, performs the batch, then pushes an event due for time 14, and so on.
The process stops when the simulation end time is reached.

Now consider a single batch.
We pop an event from the schedule and iterate through routes.
We send jams through a given route until it returns a "no slots" error.
When this happens, we mark the newly jammed hop as jammed and exclude it from consideration when generating the next route for this batch.

For the jammer's route generation, we use a generalized method.
We aim to touch as many yet unjammed target hops as possible with each next route to make jamming more efficient.
Routes may include different number of target hops (at least one).
We start from a maximum such number, specified as a parameter, for example 10.
We pick a subset of 10 unjammed target hops.
We then pick a permutation of hops in this subset.
Given a fixed permutation (that is, a list of hops), we try to construct a route that includes these hops (and potentially other hops) _in this order_.
This works as follows:
1. find a route from the sender to the first hop in the list
2. find a route from the end of the first hop to the beginning of the second hop
3. ...and so on, until either the list is depleted, or there are no sub-routes.

Note that routes may be circular.
Consider a hub-based topology, where Alice and Bob are connected to a Hub.
A target hop permutation may be: (Alice, Hub), (Hub, Alice), (Bob, Hub), (Hub, Bob).
Imagine that the sender is directly connected to Alice.
We construct the route as follows:
1. Sender - Alice
2. Sender - Alice - Hub
3. Sender - Alice - Hub - Alice
4. (searching for a sub-route from Alice to Bob, found sub-route Alice - Hub - Bob): Sender - Alice - Hub - Alice - Hub - Bob

and so on.

An alternative approach would be to filter out routes that have loops.
However, as looped payments are allowed by the protocol (citation needed) and make jamming more effective, we use them in simulations.

To recap, when constructing routes for the current jam batch, we iterate through the following nested loops:
1. for the number N of target hops in each route from some maximum (think 10) decreasing to 1;
2. for an N-sized subset of yet unjammed target hops;
3. for a permutation of this subset;
4. find a route that includes these hops in this order, and jam it;
5. Exclude the newly jammed hop from the list of yet unjammed hops, and repeat.

Even though the number of all permutations of all subsets of target hops is huge, we don't need to traverse them all.
In fact, we only need to traverse about as many routes as there are target hops.
After jamming each route, we exclude one target hop from the list of unjammed hops.
(Other hops along the route may be jammed at this point too, if they all share the same number of slots, but we can't be sure without getting an error message from them.)
Therefore, the number of path-finding operations is roughly proportional to the number of target hops (think a few thousand for the most-connected node).
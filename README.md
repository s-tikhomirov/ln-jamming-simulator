# Lightning Network Jamming Simulator

A simulator for Lightning Network payments with unconditional fees, aimed at preventing jamming attacks.

See paper: [Unjamming Lightning: A Systematic Approach](https://eprint.iacr.org/2022/1454).

## Quick start

TODO: add a guide on how to run it.


Launch with `run.py`. Some arguments that may be specified:
- whether to use one of the small testing graphs, of the full real graph
- target node: if provided, the jammer aims to jam all its adjacent nodes
- target node pairs: an alternative way to specify target node pairs is to list them explicitly
- honest senders and honest receivers: honest payment flow will be generated from a random sender node to a random receiver node (both picked uniformly for now)
- which nodes the jammer MUST send jams through - used in the experiment with jamming through a fixed route
- which nodes the jammer connects to (for sending jams from and for receiving jams to). By default, the jammer connects to all endpoints of all target node pairs.
- which nodes honest senders MUST send jams through - used in the "wheel" topology experiment to model the payment flow through the hub specifically.
- the maximum number of target node pairs per route (explained below in the routing section).


## Architecture

The general architecture is as follows:

TODO: add diagram of the architecture.

During one launch of the code, the `Simulator` executes a simulation `Scenario`.
A `Scenario` describes the network topology along with the properties of honest and malicious payments.
The goal of a simulation is to estimate the revenue of certain nodes with and without an attack.
The results are written as JSON and CSV files into `/results` (filenames include the current timestamp).

First, we prepare a `Scenario`. This involves the following:
- parse a snapshot from `/snapshots`;
- specify the honest and malicious senders and receivers, and, optionally, the target node;
- specify the list of nodes that payments must go through (optionally).

Running the `Scenario` involves running two simulations: with and without jamming.
A simulation implies, first, creating a `Schedule`, and then executing it.
A `Schedule` consists of timestamped `Events`, where each event represents an honest payment or a jam.
During execution, the simulator pops the next `Event` from the `Schedule` and executes it, until the schedule is empty.

To execute an `Event`, the simulator does the following:
- find a suitable route from the sender to the receiver for the amount required (implemented in `Router`);
- create a `Payment` for the current event and the selected route;
- send the `Payment` along the route (make up to a specified number of attempts if necessary).

Sending a `Payment` along the route involves these stages, until the payment fails or reaches the receiver:
- extract the next node from the `Payment`;
- pick a suitable `Channel` in the `Hop` towards the next node;
- store a new `Htlc` in the HTLC queue of the chosen channel in the direction needed (`ChannelDirection`);
- if there are no free slots in this `ChannelDirection`, try resolving the oldest HTLC from the queue;
- if even the HTLC with the lowest resolution time can't yet be resolved (i.e., the channel is jammed), fail the payment.

For more implementation details, see [classes.md](classes.md) and [simulation.md](simulation.md).

An example of JSON output:
```
{
    "params": {
        "scenario": "wheel",
        "num_target_node_pairs": 8,
        "duration": 30,
        "num_runs_per_simulation": 10,
        "success_base_fee": 1,
        "success_fee_rate": 5e-06,
        "no_balance_failures": false,
        "default_num_slots_per_channel_in_direction": 483,
        "max_num_attempts_per_route_honest": 10,
        "max_num_attempts_per_route_jamming": 493,
        "dust_limit": 354,
        "honest_payments_per_second": 10,
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

The numbers in `stats` are not necessarily integers, as they are averaged across multiple simulation runs.
The revenues for the jamming case in the example above are all zero, because jams fail and don't pay success-case fees.
For `upfront_base_coeff > 0` or `upfront_rate_coeff > 0`, that would not be the case.

The coefficients `upfront_base_coeff` and `upfront_rate_coeff` indicate what the unconditional fee parameters are _in proportion to the default success-case parameters_.
If the success-case fee is `1` satoshi plus `5` parts per million, `upfront_base_coeff` is 2, and `upfront_rate_coeff` is 3, then the unconditional fee would be `2` satoshi plus `15` parts per million.
(The numbers are picked just for the sake of an example; in real simulations, upfront fees are much lower.)

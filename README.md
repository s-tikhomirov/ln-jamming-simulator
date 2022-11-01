# Lightning Network Jamming Simulator

A simulator for Lightning Network payments with unconditional fees, aimed at preventing jamming attacks.

See paper: [Unjamming Lightning: A Systematic Approach](https://eprint.iacr.org/2022/1454).

## Quick start

TODO: add a guide on how to run it.

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

For more implementation details, see [classes.md](classes.md).

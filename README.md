# parallel-qsim-berlin

This is a repository containing preprocessing steps and scripts for running
the [MATSim Berlin scenario](https://github.com/matsim-scenarios/matsim-berlin).

## Preprocessing

Currently (April 2025), the parallel qsim does not implement public transport. We filter out agents performing any PT
trip.
Other modes of transport are simulated as in the original MATSim Berlin scenario.

Use:

```shell
make prepare
```

## Running the Scenario

Performs just one run of the qsim.

Note: Running the scenario relies on a local clone of the Parallel QSIM repository https://github.com/matsim-vsp/parallel_qsim_rust. You may separately wish to ensure that you can successfully build Parallel QSIM before attempting the step below which tries to do the same.

Use the following, replacing <DIR> with the path to the cloned Parallel QSIM repository:

```shell
make run RUST_BASE=<DIR>
```

In order to convert the events from protobuf to `.xml.gz` files, run

```shell
make convert-events N=<number of partitions used>
```

The default number of partitions is 16 (see config file), as this is the number of CPU cores of my computer. With this,
the QSim runs in approx. 16s. (16.04.25, 10%, no global sync, no PT)

Some other runtimes:

- 10.09.2025, 10%, no global sync, PT teleported, 16 partitions: 28s
- 10.09.2025, 10%, global sync, PT teleported, 16 partitions: 35s

## External Routing

Call RPC Raptor Routing from command line:

```shell
grpcurl -plaintext \
  -d '{"person_id": "1", "from_link_id": "1112", "to_link_id": "4142", "mode": "pt", "departure_time": 27126}' \
  localhost:50051 routing.RoutingService/GetRoute
```

Real Berlin call:

```shell
 grpcurl -plaintext \
  -d '{"person_id": "1", "from_link_id": "4597426#2", "to_link_id": "1082080800#2", "mode": "pt", "departure_time": 27126}' \
  localhost:50051 routing.RoutingService/GetRoute
```

# Open Tasks

- [ ] Explicit comparison of results with the original MATSim Berlin scenario
- [ ] Remove PT links from network
- [x] Simulate PT as teleported (one would need to convert the route types)

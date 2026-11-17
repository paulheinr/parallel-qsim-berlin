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

The Rust simulation can ask a pt router over gRPC. The router is `org.matsim.routing.RoutingServer` in this
repository; the API (`matsim.services.routing.v1`) and the shared message types come from
[matsim-schemas](https://github.com/matsim-org/matsim-schemas). Build the jar with `./mvnw package` and start the
router with a MATSim config that contains network, transit schedule and routing parameters (plans and counts are not
read):

```shell
java -jar parallel-qsim-berlin-1.0-*.jar --config path/to/config.xml --threads 4 --port 50051
```

It opens the port once all routing threads are ready, then reports `SERVING` on the standard gRPC health service
(`grpcurl -plaintext localhost:50051 grpc.health.v1.Health/Check`), and stops on the `Shutdown` call of the simulation
or on SIGTERM.

Call it from the command line (times in nanoseconds since simulation start; here the pt-tutorial scenario):

```shell
grpcurl -plaintext \
  -d '{"person_id": "1", "from_link_id": "1112", "from": {"x": 1000, "y": 1500}, "to_link_id": "4142", "to": {"x": 4000, "y": 1500}, "mode": "pt", "departure_time_ns": "27126000000000"}' \
  localhost:50051 matsim.services.routing.v1.RoutingService/GetRoute
```

For Berlin, use link ids of the Berlin network (e.g. `4597426#2` to `1082080800#2`) and their coordinates.

`Makefile` and `scripts/run-routing.sh` still start the old router and are deprecated.

# Open Tasks

- [ ] Explicit comparison of results with the original MATSim Berlin scenario
- [ ] Remove PT links from network
- [x] Simulate PT as teleported (one would need to convert the route types)

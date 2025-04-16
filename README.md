# parallel-qsim-berlin

This is a repository containing preprocessing steps and scripts for running the [MATSim Berlin scenario](https://github.com/matsim-scenarios/matsim-berlin).

## Preprocessing
Currently (April 2025), the parallel qsim does not implement public transport. We filter out agents performing any PT trip. 
Other modes of transport are simulated as in the original MATSim Berlin scenario.

Use:
```shell 
make prepare
```

## Running the Scenario
Performs just one run of the qsim. 

Use:
```shell
make run
``` 

In order to convert the events from protobuf to `.xml.gz` files, run 
```shell
make convert-events N=<number of partitions used>
```
The default number of partitions is 16 (see config file), as this is the number of CPU cores of my computer. With this, the QSim runs in approx. 16s. 

# Open Tasks
- [ ] Explicit comparison of results with the original MATSim Berlin scenario
- [ ] Remove PT links from network 
- [ ] Simulate PT as teleported (one would need to convert the route types)
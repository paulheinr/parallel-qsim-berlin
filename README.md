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

# Open Tasks
- [ ] Explicit comparison of results with the original MATSim Berlin scenario
- [ ] Simulate PT as teleported (one would need to convert the route types)
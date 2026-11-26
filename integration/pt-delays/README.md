# Scenario `pt-delays`

A small transit scenario for the development of exogenous transit delays and routing with real-time information
(see [the design document](../../docs/exogenous-pt-delays.md)). Unlike `pt-tutorial-dummy`, which has a single line
with one route per direction, it has alternatives between routes and transfers. It will grow with the development.

```
                              village
                                 |  feeder
  suburb ----- midtown -------- hub -------------------- center
     |                 local                 local, trunk    |
     +---------------------- express ------------------------+
```

Each stop has a loop link `<stop>_stop` at its node, which carries the stop facility and the activities of the
persons there, so all walks take 0 s. Only transit runs on the network.

The inputs in `input/` come unchanged from `matsim_rust/assets/pt_delays/` on the matsim-rust branch
`ph/pt-delays-scenario`, where a Rust test runs the base case. The Rust config, the scoring parameters of Rust and the
expected events of that test are still there; this directory has no `process-compose.yml` yet.

## Schedule

Departure ids are `<line>_<HHMM>` of the departure at the first stop. Each departure has a vehicle of its own with the
same id, so the events name the departure. Vehicles do not dwell at stops.

| Line | Route | Stops (minutes from the first stop) | Departures |
|---|---|---|---|
| `local` | `local_suburb_center` | suburb 0, midtown 5, hub 10, center 20 | `local_0800`, `local_0802`, `local_0810` |
| `express` | `express_suburb_center` | suburb 0, center 10 | `express_0805` |
| `feeder` | `feeder_village_hub` | village 0, hub 6 | `feeder_0800`, `feeder_0810` |
| `trunk` | `trunk_hub_center` | hub 0, center 6 | `trunk_0808`, `trunk_0815`, `trunk_0822` |

## Persons

Each person is named after what it does in the base case, without delays. Its plan in `plans.xml` is the earliest
arrival on the schedule, derived by hand.

| Person | Base case |
|---|---|
| `takes_later_but_faster_express` | leaves suburb at 07:58, lets `local_0800` (center 08:20) go and takes `express_0805`, center 08:15 |
| `transfers_with_two_minutes_at_hub` | leaves village at 07:58, `feeder_0800` to hub (08:06), `trunk_0808`, center 08:14 |
| `waits_at_hub_after_just_missing_trunk` | leaves village at 08:08, `feeder_0810` reaches hub at 08:16, one minute after `trunk_0815` left; `trunk_0822`, center 08:28 |
| `starts_at_hub_after_trunk_departed` | leaves home at hub at 08:18, after `trunk_0815` left; `trunk_0822`, center 08:28 |

Other connections are slower on purpose, e.g. `local_0810` passes hub at 08:20 but reaches center only at 08:30,
after `trunk_0822`.

## Router config

`input/router-config.xml` is the config of the Java router (SwissRailRaptor) with `useTimetableUpdates`. The
parameters that could shift the tight connections at hub are set explicitly: no extra transfer time, and the cheapest
route is the earliest arrival (waiting and riding cost the same, a transfer costs nothing extra).

## Tests

`src/test/java/org/matsim/routing/PtDelaysServerTest.java` starts the router with this config, sends snapshot 0 (the
schedule) over the timetable stream and asks for the trips of the persons over gRPC:

- **Base case:** on snapshot 0, every person gets exactly the pt legs of its plan.
- **Delay variants:** each as the delta of snapshot 1. After it, snapshot 0 still gives the base case.

| Variant | Person concerned | Route on snapshot 1 |
|---|---|---|
| `express_0805_late` (+10 min) | `takes_later_but_faster_express` | `local_0800`: the chosen express is no longer the fastest connection |
| `feeder_0800_late` (+3 min) | `transfers_with_two_minutes_at_hub` | `local_0800` from hub (08:10, center 08:20, one minute before `trunk_0815`): the connection to `trunk_0808` is lost |
| `trunk_0815_late_2min` (+2 min) | `waits_at_hub_after_just_missing_trunk` | `trunk_0815`: a connection missed before becomes reachable |
| `trunk_0815_late_5min` (+5 min) | `starts_at_hub_after_trunk_departed` | `trunk_0815`: a departure that left on schedule is still there |
| `local_0800_late` (+5 min at suburb) | none | `local_0802` has to stay behind `local_0800`; delaying `local_0800` alone breaks the contract and ends the stream |

The same test also checks waiting for snapshots, released versions, the change of iteration and client deadlines.

In matsim-rust, the same variants run in the simulation (`tests/simulation/pt_delays.rs`, see the README of
`assets/pt_delays` there), plus `local_0800_late_before_center`. Each sets delays of one departure at one stop of its
route as an attribute of the departure, one per stop: `delay_<i>` for the stop at position i of the route (from 0), a
`java.lang.String` with a JSON object of `arrivalDelayOffset` and `departureDelayOffset` (`"HH:MM:SS"`, optional, 0 by
default), e.g. `{"departureDelayOffset":"00:02:00"}`. Only the drivers of `StopDelayDriverAgentSource`, which the test
adds to the controller, carry them out. The persons follow their plans there; they do not ask the router yet.

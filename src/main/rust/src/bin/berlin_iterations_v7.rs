use clap::Parser;
use matsim_rust::simulation::config::{CommandLineArgs, CompressionType, Config, OverwriteFiles, StrategySetting};
use matsim_rust::simulation::controller::controller::ControllerBuilder;
use matsim_rust::simulation::logging::init_std_out_logging_thread_local;
use matsim_rust::simulation::replanning::DefaultStrategy;
use matsim_rust::simulation::replanning::selectors::DefaultSelector;
use matsim_rust::simulation::scenario::Scenario;
use matsim_rust::simulation::scenario::transit::{TransitRouteStop, TransitSchedule};
use std::sync::Arc;
use std::time::Duration;
use tracing::info;

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[clap(flatten)]
    delegate: CommandLineArgs,
    num_parts: usize,
    /// Seconds by which the arrival offset of every stop but the first of each transit route is moved earlier,
    /// at most to the departure offset of the previous stop. The default of 30 reproduces MATSim's QSim on the
    /// Berlin pt network, whose link speeds (CreateTransitScheduleFromGtfs, minStopTime) make vehicles reach each
    /// stop about 30 s early; passengers alight then, and vehicles wait for the scheduled departure. 0 keeps the
    /// schedule as it is.
    #[arg(long, default_value_t = 30)]
    pt_arrival_shift: u64,
}

// All subpopulations of Berlin v7.1 get the same strategies, as in the DSim runs (OpenBerlinDSimBenchmark).
const SUBPOPULATIONS: [&str; 5] = ["person", "freight", "goodsTraffic", "commercialPersonTraffic", "commercialPersonTraffic_service"];

#[hotpath::main]
fn main() {
    let _g = init_std_out_logging_thread_local();

    let args = Args::parse();
    let delegate = args.delegate;

    info!("Starting Berlin example with args: {:?}", delegate);
    let last_iteration_set = delegate.overrides.iter().any(|(key, _)| key == "controller.last_iteration");

    // load config
    let mut config = Config::from_args(delegate);
    config.output_mut().compression_type = CompressionType::Zst;
    // set directly instead of the partitioning.num_parts override, which appends "-<num_parts>" to the output dir
    config.partitioning_mut().num_parts = args.num_parts as u32;
    // one iteration by default, more with --set controller.last_iteration=<n> (inclusive)
    if !last_iteration_set {
        config.controller_mut().last_iteration = 0;
    }

    config.replanning_mut().strategy_settings.clear();
    for subpopulation in SUBPOPULATIONS {
        config.replanning_mut().strategy_settings.push(StrategySetting::new(DefaultStrategy::ReRoute.to_string(), 0.2, subpopulation.to_string()));
        config.replanning_mut().strategy_settings.push(StrategySetting::new(DefaultSelector::SelectExpBeta.to_string(), 0.8, subpopulation.to_string()));
    }
    config.computational_setup_mut().replanning_threads = args.num_parts as u32;
    config.computational_setup_mut().scoring_threads = args.num_parts as u32;

    config.routing_mut().network_modes.append(&mut vec!["bike", "car", "truck", "ride", "freight"].iter().map(|s| s.to_string()).collect());

    // config.computational_setup_mut().global_sync = true;
    config.output_mut().overwrite_files = OverwriteFiles::DeleteDirectoryIfExists;
    let config = Arc::new(config);

    // load scenario, the scoring parameters come from scoring.scoring_parameters_path of the config
    let mut scenario = Scenario::load(config.clone());
    // only the selected plans are kept, as in OpenBerlinDSimBenchmark
    for person in scenario.population.persons.values_mut() {
        person.plans_mut().retain(|plan| plan.selected);
    }
    if args.pt_arrival_shift > 0 && !scenario.transit_schedule.is_empty() {
        shift_arrival_offsets(&mut scenario.transit_schedule, Duration::from_secs(args.pt_arrival_shift));
    }

    // create controller
    // ride is teleported along its network route and freight drives on the network as its own mode, so the routers use
    // the travel times of car and truck, as OpenBerlinScenario binds them in Java. bike keeps its free speed travel
    // times (bounded by the maximum speed of the bike vehicle).
    ControllerBuilder::default_with_scenario(scenario)
        .travel_time_mode("ride", "car")
        .travel_time_mode("freight", "truck")
        .build().unwrap().run();

    // matsim_rust::simulation::events::utils::convert_proto_to_xml_events(
    //     config.output().output_dir.join("events"),
    //     config.partitioning().num_parts,
    //     config.output().output_dir.join("output_events.xml.zst"),
    // )
    //     .unwrap()
}


/// Moves the arrival offset of every stop but the first of each route of `schedule` `shift` earlier, but not earlier
/// than the departure offset of the previous stop (as given in the schedule). A stop without arrival offset gets one,
/// shifted from its departure offset. The router of later iterations sees the shifted arrivals too (Java's
/// SwissRailRaptor routes on the original schedule).
fn shift_arrival_offsets(schedule: &mut TransitSchedule, shift: Duration) {
    let (mut shifted, mut clamped) = (0usize, 0usize);
    for stops in schedule.route_stops_mut() {
        let (s, c) = shift_stops(stops, shift);
        shifted += s;
        clamped += c;
    }
    info!(
        "Moved the arrival offsets of {shifted} transit route stops {} s earlier, {clamped} of them only to the departure \
         offset of the previous stop.",
        shift.as_secs()
    );
}

/// Shifts the arrival offsets of `stops` (one route) as described in [`shift_arrival_offsets`]. Returns the number of
/// shifted stops and how many of them were limited by the previous departure.
fn shift_stops(stops: &mut [TransitRouteStop], shift: Duration) -> (usize, usize) {
    let (mut shifted, mut clamped) = (0, 0);
    let mut previous_departure: Option<Duration> = None;
    for stop in stops.iter_mut() {
        let Some(arrival) = stop.arrival() else {
            previous_departure = None;
            continue;
        };
        let departure = stop.departure().unwrap_or(arrival);
        if let Some(previous) = previous_departure {
            let mut new_arrival = arrival.saturating_sub(shift);
            if new_arrival < previous {
                new_arrival = previous;
                clamped += 1;
            }
            stop.arrival_offset = Some(new_arrival);
            shifted += 1;
        }
        previous_departure = Some(departure);
    }
    (shifted, clamped)
}

#[cfg(test)]
mod tests {
    use super::*;
    use matsim_rust::simulation::InternalAttributes;

    fn stop(arrival: Option<u64>, departure: Option<u64>) -> TransitRouteStop {
        TransitRouteStop {
            arrival_offset: arrival.map(Duration::from_secs),
            departure_offset: departure.map(Duration::from_secs),
            await_departure: Some(true),
            allow_boarding: true,
            allow_alighting: true,
            minimum_stop_duration: Duration::ZERO,
            attributes: InternalAttributes::default(),
        }
    }

    #[test]
    fn shifts_arrivals_but_not_the_first_stop_and_not_before_the_previous_departure() {
        let mut stops = vec![
            stop(Some(0), Some(0)),
            stop(Some(300), Some(300)),
            stop(Some(320), Some(360)),
            stop(None, Some(480)),
            stop(Some(600), None),
        ];
        assert_eq!(shift_stops(&mut stops, Duration::from_secs(30)), (4, 1));
        let arrivals: Vec<_> = stops.iter().map(|s| s.arrival_offset.map(|d| d.as_secs())).collect();
        assert_eq!(arrivals, vec![Some(0), Some(270), Some(300), Some(450), Some(570)]);
        let departures: Vec<_> = stops.iter().map(|s| s.departure_offset.map(|d| d.as_secs())).collect();
        assert_eq!(departures, vec![Some(0), Some(300), Some(360), Some(480), None]);
    }
}

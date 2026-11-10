use clap::Parser;
use matsim_rust::simulation::config::{CommandLineArgs, CompressionType, Config, OverwriteFiles, StrategySetting};
use matsim_rust::simulation::controller::controller::ControllerBuilder;
use matsim_rust::simulation::logging::init_std_out_logging_thread_local;
use matsim_rust::simulation::replanning::DefaultStrategy;
use matsim_rust::simulation::replanning::selectors::DefaultSelector;
use matsim_rust::simulation::scenario::Scenario;
use std::sync::Arc;
use tracing::info;

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[clap(flatten)]
    delegate: CommandLineArgs,
    num_parts: usize,
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

    // create controller
    ControllerBuilder::default_with_scenario(scenario)
        .build().unwrap().run();

    // matsim_rust::simulation::events::utils::convert_proto_to_xml_events(
    //     config.output().output_dir.join("events"),
    //     config.partitioning().num_parts,
    //     config.output().output_dir.join("output_events.xml.zst"),
    // )
    //     .unwrap()
}


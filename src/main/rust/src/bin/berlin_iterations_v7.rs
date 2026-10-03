use clap::Parser;
use rust_qsim::simulation::config::{CommandLineArgs, Config, ModeParameter, OverwriteFiles, StrategySetting};
use rust_qsim::simulation::controller::controller::ControllerBuilder;
use rust_qsim::simulation::id::Id;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::replanning::DefaultStrategy;
use rust_qsim::simulation::replanning::selectors::DefaultSelector;
use rust_qsim::simulation::scenario::Scenario;
use rust_qsim::simulation::scenario::network::Link;
use rust_qsim::simulation::scenario::population::InternalPlanElement;
use rust_qsim::simulation::scoring::OnlyTravelTimeDependentScoring;
use std::sync::Arc;
use tracing::info;

fn main() {
    let _g = init_std_out_logging_thread_local();

    let mut args = CommandLineArgs::parse();
    args.overrides.push(("partitioning.num_parts".to_string(), "16".to_string()));

    info!("Starting Berlin example with args: {:?}", args);

    // load config
    let mut config = Config::from_args(args);
    config.controller_mut().last_iteration = 1;
    config.scoring_mut().mode_params.clear();
    config.scoring_mut().mode_params.push(ModeParameter::default_for_mode("car"));
    config.scoring_mut().mode_params.push(ModeParameter::default_for_mode("truck"));
    config.scoring_mut().mode_params.push(ModeParameter::default_for_mode("freight"));
    config.scoring_mut().mode_params.push(ModeParameter::default_for_mode("bike"));
    config.scoring_mut().mode_params.push(ModeParameter::default_for_mode("ride"));

    config.replanning_mut().strategy_settings.clear();
    config.replanning_mut().strategy_settings.push(StrategySetting::new(DefaultStrategy::ReRoute.to_string(), 0.2, "person".to_string()));
    config.replanning_mut().strategy_settings.push(StrategySetting::new(DefaultSelector::SelectExpBeta.to_string(), 0.8, "person".to_string()));
    config.computational_setup_mut().replanning_threads = 16;
    config.computational_setup_mut().scoring_threads = 16;

    config.routing_mut().network_modes.append(&mut vec!["bike", "car", "truck", "ride", "freight"].iter().map(|s| s.to_string()).collect());

    // config.computational_setup_mut().global_sync = true;
    config.output_mut().overwrite_files = OverwriteFiles::DeleteDirectoryIfExists;
    let config = Arc::new(config);

    // load scenario
    let mut scenario = Scenario::load(config.clone());
    // scenario
    //     .population
    //     .persons
    //     .retain(|i, _| i.external().eq("berlin_46ea2b4a"));
    scenario
        .population
        .persons
        .retain(|_, p| p.plans()
            .iter()
            .flat_map(|plan| plan.elements.iter())
            .all(|element| match element {
                InternalPlanElement::Activity(_) => true,
                InternalPlanElement::Leg(l) => !l.routing_mode.eq(&Some(Id::create("pt"))),
            }));

    add_dummy_link(&mut scenario);

    // create controller
    ControllerBuilder::default_with_scenario(scenario).scoring_function(Box::new(OnlyTravelTimeDependentScoring)).build().unwrap().run();

    // rust_qsim::simulation::events::utils::convert_proto_to_xml_events(
    //     config.output().output_dir.join("events"),
    //     config.partitioning().num_parts,
    //     config.output().output_dir.join("output_events.xml.zst"),
    // )
    //     .unwrap()
}

// Adds a dummy link between PT and car network at Gotzkowskybrücke
fn add_dummy_link(scenario: &mut Scenario) {
    let partition = scenario
        .network
        .get_node(&Id::get_from_ext("pt_648553_bus"))
        .partition;

    scenario.network.add_link(Link {
        id: Id::create("pt-connection"),
        from: Id::get_from_ext("pt_648553_bus"),
        to: Id::get_from_ext("cluster_1807917065_1929624603_1929624605_29962151_#3more"),
        length: 1.0,
        capacity: 0.0,
        freespeed: 0.0,
        permlanes: 1.0,
        modes: Default::default(),
        partition,
        attributes: Default::default(),
    });
}

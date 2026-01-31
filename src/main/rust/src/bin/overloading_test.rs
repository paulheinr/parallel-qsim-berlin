use rust_qsim::simulation::config::{Config, Network, Population, Vehicles, WriteEvents};
use rust_qsim::simulation::controller::local_controller::LocalControllerBuilder;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::scenario::GlobalScenario;
use std::path::PathBuf;
use std::sync::Arc;

fn main() {
    let _g = init_std_out_logging_thread_local();

    let rate = 0.03;
    let sample = 0.01;

    let mut config = Config::default();
    config.simulation_mut().stuck_threshold = 30;
    config.simulation_mut().sample_size = sample;
    let output = config.output_mut();
    output.output_dir = PathBuf::from(format!(
        "../../../output/overloading_test-rust-r{:}-s{sample}",
        rate
    ));
    output.write_events = WriteEvents::XmlGz;

    config.set_population(Population {
        path: PathBuf::from(format!(
            "../../../output/overloading-test-r{:}-s{sample}/output_plans.xml.gz",
            rate
        )),
    });
    config.set_network(Network {
        path: PathBuf::from(format!(
            "../../../output/overloading-test-r{:}-s{sample}/output_network.xml.gz",
            rate
        )),
    });
    config.set_vehicles(Vehicles {
        path: PathBuf::from(format!(
            "../../../output/overloading-test-r{:}-s{sample}/output_vehicles.xml.gz",
            rate
        )),
    });

    let scenario = GlobalScenario::load(Arc::new(config));
    let controller = LocalControllerBuilder::default()
        .global_scenario(scenario)
        .build()
        .unwrap();
    controller.run_and_join_handles();
}

use rust_qsim::simulation::config::{Config, Network, Population, Vehicles, WriteEvents};
use rust_qsim::simulation::controller::controller::ControllerBuilder;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::scenario::MutableScenario;
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
        path: Option::from(PathBuf::from(format!(
            "../../../output/overloading-test-r{:}-s{sample}/output_plans.xml.gz",
            rate
        ))),
    });
    config.set_network(Network {
        path: Option::from(PathBuf::from(format!(
            "../../../output/overloading-test-r{:}-s{sample}/output_network.xml.gz",
            rate
        ))),
    });
    config.set_vehicles(Vehicles {
        path: Option::from(PathBuf::from(format!(
            "../../../output/overloading-test-r{:}-s{sample}/output_vehicles.xml.gz",
            rate
        ))),
    });

    let scenario = MutableScenario::load(Arc::new(config));
    let controller = ControllerBuilder::default_with_scenario(scenario)
        .build()
        .unwrap();
    controller.run();
}

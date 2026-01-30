use rust_qsim::simulation::config::{Config, ProtoFiles};
use rust_qsim::simulation::controller::local_controller::LocalControllerBuilder;
use rust_qsim::simulation::scenario::GlobalScenario;
use std::path::PathBuf;
use std::sync::Arc;

fn main() {
    let mut config = Config::default();
    config.simulation().stuck_threshold = 30;
    config.output().output_dir = PathBuf::from("./output/overloading_test-rust");
    config.set_proto_files(ProtoFiles {
        network: PathBuf::from("./output/overloading-test-1/output_network.xml.gz"),
        population: PathBuf::from("./output/overloading-test-1/output_plans.xml.gz"),
        vehicles: Default::default(),
        ids: Default::default(),
    });

    let scenario = GlobalScenario::load(Arc::new(config));
    let controller = LocalControllerBuilder::default()
        .global_scenario(scenario)
        .build()
        .unwrap();
    controller.run();
}

use rust_qsim::simulation::config::Config;
use rust_qsim::simulation::controller::local_controller::LocalControllerBuilder;
use rust_qsim::simulation::id::Id;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::scenario::GlobalScenario;
use rust_qsim::simulation::vehicles::InternalVehicleType;
use std::path::PathBuf;
use std::sync::Arc;

fn main() {
    let _g = init_std_out_logging_thread_local();

    let config = Config::from(PathBuf::from(
        "/Users/paulh/git/matsim-berlin-ph/input/v6.4/rust-qsim-config.yml",
    ));

    let mut scenario = GlobalScenario::load(Arc::new(config));
    let id = Id::create("walk");
    scenario.garage.vehicle_types.insert(
        id.clone(),
        InternalVehicleType {
            id,
            length: 1.,
            width: 1.,
            max_v: 0.833,
            pce: 0.1,
            fef: 0.0,
            net_mode: Id::create("walk"),
            attributes: Default::default(),
        },
    );

    scenario.population.persons.keys().for_each(|id| {
        scenario.garage.vehicles.insert(
            Id::create(&format!("{}_walk", id)),
            rust_qsim::simulation::vehicles::InternalVehicle {
                id: Id::create(&format!("{}-walk", id)),
                max_v: 0.833,
                pce: 0.1,
                driver: None,
                passengers: vec![],
                vehicle_type: Id::create("walk"),
                attributes: Default::default(),
            },
        );
    });

    LocalControllerBuilder::default()
        .global_scenario(scenario)
        .build()
        .unwrap()
        .run_and_join_handles();
}

//! Runs the pt tutorial with pt routed during the simulation by an external router, like
//! `berlin_iterations_v7 --router-ip`. Moved here from matsim-rust (`tests/simulation/pt.rs`), where the router
//! does not live. The tests only check that the simulation runs through.
//!
//! They need a router on localhost:50051, e.g. the one of this repository, started from the repository root after
//! `./mvnw package`:
//!
//! ```shell
//! java -jar parallel-qsim-berlin-1.0-*.jar --config src/main/rust/tests/resources/pt_tutorial/config.xml
//! ```
//!
//! The simulation stops the router at its end (Shutdown), so start the router again for each test and run one test
//! at a time, in `src/main/rust`:
//!
//! ```shell
//! cargo test --test pt_adaptive pt_adaptive_with_dummy -- --ignored
//! ```

use matsim_rust::external_services::routing::RoutingServiceAdapterFactory;
use matsim_rust::external_services::{AdapterHandleBuilder, AsyncExecutor, ExternalServiceType};
use matsim_rust::simulation::config::{CommandLineArgs, Config};
use matsim_rust::simulation::controller::ExternalServices;
use matsim_rust::simulation::controller::controller::ControllerBuilder;
use matsim_rust::simulation::logging::init_std_out_logging_thread_local;
use matsim_rust::simulation::population::agent_source::PreplanningHorizonAgentSource;
use matsim_rust::simulation::scenario::Scenario;
use std::path::PathBuf;
use std::sync::{Arc, Barrier};

const RESOURCES: &str = "./tests/resources/pt_tutorial";
const ROUTER: &str = "http://localhost:50051";

#[test]
#[ignore = "needs a router on localhost:50051, see the module documentation"]
fn pt_adaptive_with_access_egress() {
    run_pt_adaptive("plans_1-access_egress");
}

#[test]
#[ignore = "needs a router on localhost:50051, see the module documentation"]
fn pt_adaptive_with_dummy() {
    run_pt_adaptive("plans_1-dummy");
}

/// Runs the tutorial with the population `<plans>.xml` and writes the output to `output/pt_adaptive/<plans>`.
fn run_pt_adaptive(plans: &str) {
    let _guard = init_std_out_logging_thread_local();

    let mut config = Config::from_args(CommandLineArgs::new_with_path(format!(
        "{RESOURCES}/pt_tutorial_config_adaptive.yml"
    )));
    config.population_mut().path = Some(PathBuf::from(format!("{RESOURCES}/{plans}.xml")));
    config.output_mut().output_dir = PathBuf::from(format!("./output/pt_adaptive/{plans}"));
    let config = Arc::new(config);

    // The mobsim workers and the routing adapter wait for each other once before the first iteration, so that the
    // mobsim starts only when the router is connected.
    let global_barrier = Arc::new(Barrier::new(config.partitioning().num_parts as usize + 1));
    let executor = AsyncExecutor::from_config(&config, global_barrier.clone());
    let routing_factory = RoutingServiceAdapterFactory::new(
        vec![ROUTER],
        config.clone(),
        executor.shutdown_handles(),
    );
    let (handle, send, shutdown) = executor.spawn_thread("routing_adapter", routing_factory);

    let mut services = ExternalServices::default();
    services.insert(ExternalServiceType::Routing("pt".into()), send.into());

    let scenario = Scenario::load(config);
    ControllerBuilder::default_with_scenario(scenario)
        .external_services(services)
        .global_barrier(global_barrier)
        .agent_sources(vec![Arc::new(PreplanningHorizonAgentSource)])
        .adapter_handles(vec![
            AdapterHandleBuilder::default()
                .shutdown_sender(shutdown)
                .handle(handle)
                .build()
                .unwrap(),
        ])
        .build()
        .unwrap()
        .run();
}

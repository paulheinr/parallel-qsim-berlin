use clap::Parser;
use rust_qsim::simulation::config::{CommandLineArgs, Config};
use rust_qsim::simulation::controller::controller::ControllerBuilder;
use rust_qsim::simulation::id::Id;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::scenario::network::Link;
use rust_qsim::simulation::scenario::population::PREPLANNING_HORIZON;
use rust_qsim::simulation::scenario::vehicles::InternalVehicleType;
use rust_qsim::simulation::scenario::{trip_structure_utils, MutableScenario};

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
struct BerlinCommandLineArgs {
    #[clap(flatten)]
    delegate: CommandLineArgs,
    #[clap(long, short)]
    horizon: Option<usize>,
}

fn main() {
    let _g = init_std_out_logging_thread_local();

    let args = BerlinCommandLineArgs::parse();

    let config = Config::from_args(args.delegate);
    let mut scenario = MutableScenario::load(config);

    add_walk_vehicle(&mut scenario);
    add_dummy_link(&mut scenario);
    if let Some(horizon) = args.horizon {
        add_preplanning_horizon(&mut scenario, horizon);
    }

    ControllerBuilder::default_with_scenario(scenario)
        .build()
        .unwrap()
        .run();
}

fn add_preplanning_horizon(scenario: &mut MutableScenario, horizon: usize) {
    for (_, person) in &mut scenario.population.persons {
        let spans =
            trip_structure_utils::get_trip_spans_default(&person.selected_plan().unwrap().elements);
        for span in spans {
            let elements = span.trip_elements(&person.selected_plan().unwrap().elements);
            let mode = trip_structure_utils::identify_main_mode(elements)
                .expect("could not identify main mode");
            if mode.eq("pt") {
                span.origin_mut(&mut person.selected_plan_mut().elements)
                    .attributes
                    .insert(PREPLANNING_HORIZON, horizon.to_string());
            }
        }
    }
}

// Adds a dummy link between PT and car network at Gotzkowskybrücke
fn add_dummy_link(scenario: &mut MutableScenario) {
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

fn add_walk_vehicle(mut scenario: &mut MutableScenario) {
    let id = Id::create("walk");
    scenario.garage.vehicle_types.insert(
        id.clone(),
        InternalVehicleType {
            id,
            length: 1.,
            width: 1.,
            max_v: 1.23,
            pce: 0.1,
            fef: 0.0,
            net_mode: Id::create("walk"),
            attributes: Default::default(),
        },
    );

    scenario.population.persons.keys().for_each(|id| {
        scenario.garage.vehicles.insert(
            Id::create(&format!("{}_walk", id)),
            rust_qsim::simulation::scenario::vehicles::InternalVehicle {
                id: Id::create(&format!("{}-walk", id)),
                max_v: 0.833,
                pce: 0.1,
                vehicle_type: Id::create("walk"),
                attributes: Default::default(),
            },
        );
    });
}

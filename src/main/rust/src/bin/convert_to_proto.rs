use rust_qsim::simulation::config::PartitionMethod;
use rust_qsim::simulation::io::xml::population::{IOPlanElement, IOPopulation};
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::scenario::network::Network;
use rust_qsim::simulation::scenario::population::Population;
use rust_qsim::simulation::scenario::transit::TransitSchedule;
use rust_qsim::simulation::scenario::vehicles::Garage;
use rust_qsim::utilities::convert_to_binary::InputArgs;
use std::path::PathBuf;
use tracing::info;

fn main() {
    let _g = init_std_out_logging_thread_local();
    let base_input_path = PathBuf::from("../../../../../public-svn/matsim/scenarios/countries/de/berlin/berlin-v7.1");
    let output_path = PathBuf::from("/Users/paulh/shared-svn/projects/rust-qsim/berlin-v7.1");

    let pct = "10pct";
    let folder = base_input_path.join(format!("calibrated-{}/output/", pct));
    let net_file = format!("berlin-v7.1-{}.output_network.xml.gz", pct);
    let pop_file = format!("berlin-v7.1-{}.output_plans.xml.gz", pct);
    let vehicles = format!("berlin-v7.1-{}.output_vehicles.xml.gz", pct);
    let transit_schedule = format!("berlin-v7.1-{}.output_transitSchedule.xml.gz", pct);

    let args = InputArgs {
        network: folder.join(net_file),
        population: folder.join(pop_file),
        vehicles: folder.join(vehicles),
        output_dir: output_path.join(pct),
        run_id: "berlin-v7.1".to_string(),
        transit_schedule: Some(folder.join(transit_schedule)),
    };

    let mut veh = Garage::from_file(&args.vehicles);
    let mut net = Network::from_file_path(&args.network, 1, &PartitionMethod::None);
    let transit_schedule1 = args
        .transit_schedule
        .as_ref()
        .map(|path| TransitSchedule::from_file(path));

    let mut io_pop = IOPopulation::from_file(&args.population);
    let total_persons = io_pop.persons.len();
    io_pop.persons.retain(|person| {
        person
            .plans
            .iter()
            .flat_map(|plan| plan.elements.iter())
            .all(|element| match element {
                IOPlanElement::Activity(activity) => activity.link.is_some(),
                IOPlanElement::Leg(_) => true,
            })
    });
    info!(
        "Removed {} of {} persons because at least one activity has no link id",
        total_persons - io_pop.persons.len(),
        total_persons
    );

    let filter_pop_file = args.output_dir.join(format!("population-filtered.{}.xml.zst", pct));
    io_pop.to_file(&filter_pop_file);

    let pop = Population::from_file(filter_pop_file, &mut veh);

    rust_qsim::simulation::id::store_to_file(&create_file_path(&&args, "ids"));
    net.to_file(&create_file_path(&&args, "network"));
    veh.to_file(&create_file_path(&&args, "vehicles"));
    pop.to_file(&create_file_path(&&args, "plans"));
    if let Some(transit_schedule) = transit_schedule1.as_ref() {
        transit_schedule.to_file(&create_file_path(&&args, "transit_schedule"));
    }
}

fn create_file_path(args: &InputArgs, extension: &str) -> PathBuf {
    args.output_dir
        .join(format!("{}.{}.binpb", args.run_id, extension))
}

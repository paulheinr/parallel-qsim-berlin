use matsim_rust::simulation::logging::init_std_out_logging_thread_local;
use matsim_rust::utilities::convert_to_binary;
use matsim_rust::utilities::convert_to_binary::InputArgs;
use std::path::PathBuf;

fn main() {
    let _g = init_std_out_logging_thread_local();
    let base_input_path = PathBuf::from("../../../../../public-svn/matsim/scenarios/countries/de/berlin/berlin-v7.1");
    let output_path = PathBuf::from("/Users/paulh/shared-svn/projects/rust-qsim/berlin-v7.1");
    // let output_path = PathBuf::from("../../../output/v7.1/1pct/berlin_27797753");

    let pct = "10pct";
    let folder = base_input_path.join(format!("calibrated-{}/output/", pct));
    let net_file = format!("berlin-v7.1-{}.output_network.xml.gz", pct);
    let pop_file = format!("berlin-v7.1-{}.output_plans.xml.gz", pct);
    let veh_file = format!("berlin-v7.1-{}.output_vehicles.xml.gz", pct);
    let facilities_file = format!("berlin-v7.1-{}.output_facilities.xml.gz", pct);
    let transit_schedule_file = format!("berlin-v7.1-{}.output_transitSchedule.xml.gz", pct);


    let args = InputArgs {
        network: folder.join(net_file),
        population: folder.join(pop_file),
        vehicles: folder.join(veh_file),
        output_dir: output_path.join(pct),
        run_id: "berlin-v7.1".to_string(),
        transit_schedule: Some(folder.join(transit_schedule_file)),
        facilities: Some(folder.join(facilities_file)),
    };

    convert_to_binary::run(&args, |_, pop, _, _, _| {
        // pop.persons.retain(|p, _| p.external().eq("berlin_27797753"))
    });
}
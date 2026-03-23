use rust_qsim::simulation::id;
use rust_qsim::simulation::id::Id;
use rust_qsim::simulation::logging::init_std_out_logging_thread_local;
use rust_qsim::simulation::scenario::population::Population;
use rust_qsim::simulation::scenario::vehicles::Garage;
use std::path::PathBuf;
use tracing::info;

fn main() {
    let g = init_std_out_logging_thread_local();

    info!("Loading id store.");
    id::load_from_file(&PathBuf::from(
        "/Users/paulh/shared-svn/projects/rust-qsim/1pct/binpb/berlin-v6.4-1pct.ids.binpb",
    ));

    info!("Loading garage.");
    let mut garage = Garage::from_file(&PathBuf::from(
        "/Users/paulh/shared-svn/projects/rust-qsim/1pct/binpb/berlin-v6.4-1pct.vehicles.binpb",
    ));

    info!("Loading population.");
    let population = Population::from_file(
        &PathBuf::from(
            "/Users/paulh/shared-svn/projects/rust-qsim/1pct/binpb/berlin-v6.4-1pct.plans.binpb",
        ),
        &mut garage,
    );

    info!("Filter pop");
    let person = population
        .persons
        .get(&Id::get_from_ext("berlin_423098b6"))
        .unwrap();

    println!("{:#?}", person);

    drop(g);
}

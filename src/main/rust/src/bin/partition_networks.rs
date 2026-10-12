use clap::Parser;
use matsim_rust::simulation::config::{NonMainModeLinks, PartitionMethod, Partitioning};
use matsim_rust::simulation::logging::init_std_out_logging_thread_local;
use matsim_rust::simulation::scenario::network::Network;
use rayon::prelude::*;
use std::fs;
use std::fs::File;
use std::path::{Path, PathBuf};
use tracing::info;

/// Partitions a network once for every number of parts in `from..=to` and writes one file per number of parts:
/// `<output_dir>/<prefix>.<label>.<NNN>.xml.zst`. The label is the file stem of the method file.
///
/// The simulation uses such a file with `--set network.path=<file> --set partitioning.method=none`.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Input network, e.g. berlin-v7.1-1pct.output_network.xml.gz
    #[arg(long)]
    network: PathBuf,
    /// Partition method as YAML, e.g. input/partitioning/metis.yml
    #[arg(long)]
    method: PathBuf,
    #[arg(long)]
    output_dir: PathBuf,
    /// Prefix of the output file names. Defaults to the input file name without extension.
    #[arg(long)]
    prefix: Option<String>,
    #[arg(long, default_value_t = 1)]
    from: u32,
    #[arg(long, default_value_t = 192)]
    to: u32,
    /// Don't partition again if the output file already exists.
    #[arg(long)]
    skip_existing: bool,
}

fn main() {
    let _g = init_std_out_logging_thread_local();
    let args = Args::parse();
    assert!(
        1 <= args.from && args.from <= args.to,
        "Invalid range: from ({}) must be at least 1 and at most to ({}).",
        args.from,
        args.to
    );

    let method_file = File::open(&args.method)
        .unwrap_or_else(|e| panic!("Could not open method file {:?}: {e}", args.method));
    let method: PartitionMethod = serde_yaml::from_reader(method_file)
        .unwrap_or_else(|e| panic!("Could not parse method file {:?}: {e}", args.method));
    assert_ne!(
        method,
        PartitionMethod::None,
        "Partition method None does not partition anything."
    );

    let label = args.method.file_stem().unwrap().to_str().unwrap();
    let prefix = args
        .prefix
        .clone()
        .unwrap_or_else(|| strip_network_extension(&args.network));

    info!("Partitioning {:?} with {label}: {method:?}", args.network);
    fs::create_dir_all(&args.output_dir).unwrap();
    let network = Network::from_file(&args.network);

    // logging is thread-local, so pass the subscriber on to the rayon worker threads.
    let dispatch = tracing::dispatcher::get_default(|d| d.clone());
    (args.from..=args.to).into_par_iter().for_each(|num_parts| {
        let _g = tracing::dispatcher::set_default(&dispatch);
        let out_path = args
            .output_dir
            .join(format!("{prefix}.{label}.{num_parts:03}.xml.zst"));
        if args.skip_existing && out_path.exists() {
            info!("Skipping {out_path:?}, it already exists.");
            return;
        }

        let partitioning = Partitioning {
            num_parts,
            method: method.clone(),
            non_main_mode_links: NonMainModeLinks::AssignAfterPartitioningToNearest,
        };

        let mut partitioned = network.clone();
        Network::partition_network(&mut partitioned, &partitioning, &vec![String::from("car"), String::from("freight"), String::from("truck"), String::from("bike")]);

        // write to a temporary file first, so that an interrupted run does not leave a truncated file which
        // would be skipped with --skip-existing.
        let tmp_path = args
            .output_dir
            .join(format!("{prefix}.{label}.{num_parts:03}.tmp.xml.zst"));
        partitioned.to_file(&tmp_path);
        fs::rename(&tmp_path, &out_path).unwrap();
        info!("Wrote network with {num_parts} partitions to {out_path:?}");
    });
}

fn strip_network_extension(path: &Path) -> String {
    let file_name = path.file_name().unwrap().to_str().unwrap();
    [".xml.gz", ".xml.zst", ".xml", ".binpb"]
        .iter()
        .find_map(|ext| file_name.strip_suffix(ext))
        .unwrap_or(file_name)
        .to_string()
}

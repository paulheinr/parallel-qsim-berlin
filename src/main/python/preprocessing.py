import argparse

from load import aggregate_instrument_timebins, discover_runs, RunMeta, aggregate_routing


def preprocess_data(run_list: list[RunMeta], instrument: bool = True, routing: bool = True):
    for run in run_list:
        print(f"Processing run at: {run.path}")

        if instrument:
            aggregate_instrument_timebins(run, bin_size=30)

        if routing:
            aggregate_routing(run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preprocess instrument data and aggregate."
    )

    parser.add_argument("root", help="root directory containing instrument data runs")
    parser.add_argument("instrument", default="true", )
    parser.add_argument("routing", default="true", )

    args = parser.parse_args()
    runs = discover_runs(args.root)
    print(f"Found runs at {[run.path for run in runs]}")
    preprocess_data(runs, routing=args.routing, instrument=args.instrument)

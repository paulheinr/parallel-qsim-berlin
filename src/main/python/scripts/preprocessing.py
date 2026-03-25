import argparse
from pathlib import Path

from load import aggregate_instrument_timebins, discover_runs, RunMeta, aggregate_routing


def preprocess_data(run_list: list[RunMeta], instrument: bool = True, routing: bool = True, lazy: bool = True):
    for run in run_list:
        print(f"Processing run at: {run.path}")

        routing_path = Path(run.path / "instrument" / "routing_aggregated.parquet")
        instrument_path = Path(run.path / "instrument" / "routing_aggregated.parquet")

        if instrument and (not lazy or not instrument_path.exists()):
            aggregate_instrument_timebins(run, bin_size=30)

        if routing and (not lazy or not routing_path.exists()):
            aggregate_routing(run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preprocess instrument data and aggregate."
    )

    parser.add_argument("--root", help="root directory containing instrument data runs")

    parser.add_argument(
        "--no-instrument",
        dest="instrument",
        action="store_false",
        help="Disable instrumentation"
    )
    parser.set_defaults(instrument=True)

    parser.add_argument(
        "--no-routing",
        dest="routing",
        action="store_false",
        help="Disable routing"
    )
    parser.set_defaults(routing=True)

    parser.add_argument("--dry", default=False, type=bool)
    parser.add_argument("--lazy", default=True, type=bool)

    args = parser.parse_args()

    print(f"Discovering runs with args: {args}")

    runs = discover_runs(args.root)
    print(f"Found runs at {[run.path for run in runs]}")

    if not args.dry:
        preprocess_data(runs, routing=args.routing, instrument=args.instrument, lazy=args.lazy)

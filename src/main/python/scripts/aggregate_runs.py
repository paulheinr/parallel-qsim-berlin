#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from load_utils import aggregate_qsim, aggregate_routing, discover


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate routing and qsim outputs for discovered runs."
    )
    parser.add_argument(
        "root",
        type=Path,
        help="Folder containing run directories such as sim..._sim and sim..._serverN",
    )
    parser.add_argument(
        "--bin-size",
        type=int,
        default=20,
        help="QSim aggregation bin size in simulation time units.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a run when both aggregated output files already exist.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at the first run that fails instead of continuing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root

    if not root.is_dir():
        raise NotADirectoryError(root)

    runs = discover(root)
    print(f"Discovered {len(runs)} runs in {root}")

    succeeded = 0
    failed = 0

    for index, run in enumerate(runs, start=1):
        routing_output = run.instrument_path / "routing_aggregated.parquet"
        qsim_output = run.instrument_path / "instrument_aggregated.parquet"

        if args.skip_existing and routing_output.exists() and qsim_output.exists():
            print(f"[{index}/{len(runs)}] Skipping {run.run_id}: aggregated files already exist")
            succeeded += 1
            continue

        print(f"[{index}/{len(runs)}] Aggregating {run.run_id}")
        try:
            aggregate_routing(run, output=True)
            aggregate_qsim(run, bin_size=args.bin_size, output=True)
            succeeded += 1
        except Exception as exc:
            failed += 1
            print(f"[{index}/{len(runs)}] Failed {run.run_id}: {exc}")
            if args.fail_fast:
                raise

    print(
        f"Finished aggregation in {root}. "
        f"Succeeded: {succeeded}, failed: {failed}, total: {len(runs)}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        "--threads",
        type=int,
        default=1,
        help="Number of runs to aggregate in parallel.",
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


def aggregate_one_run(run, bin_size: int, skip_existing: bool) -> tuple[str, str]:
    routing_output = run.instrument_path / "routing_aggregated.parquet"
    qsim_output = run.instrument_path / "instrument_aggregated.parquet"

    if skip_existing and routing_output.exists() and qsim_output.exists():
        return run.run_id, "skipped"

    aggregate_routing(run, output=True)
    aggregate_qsim(run, bin_size=bin_size, output=True)
    return run.run_id, "aggregated"


def main() -> int:
    args = parse_args()
    root = args.root

    print(f"Starting with args: {args}")

    if not root.is_dir():
        raise NotADirectoryError(root)
    if args.threads < 1:
        raise ValueError("--threads must be at least 1")

    runs = discover(root)
    print(f"Discovered {len(runs)} runs in {root}")

    succeeded = 0
    failed = 0

    if args.threads == 1:
        for index, run in enumerate(runs, start=1):
            print(f"[{index}/{len(runs)}] Aggregating {run.run_id}")
            try:
                run_id, status = aggregate_one_run(run, args.bin_size, args.skip_existing)
                if status == "skipped":
                    print(f"[{index}/{len(runs)}] Skipping {run_id}: aggregated files already exist")
                else:
                    print(f"[{index}/{len(runs)}] Finished {run_id}")
                succeeded += 1
            except Exception as exc:
                failed += 1
                print(f"[{index}/{len(runs)}] Failed {run.run_id}: {exc}")
                if args.fail_fast:
                    raise
    else:
        future_to_run = {}
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            for run in runs:
                future = executor.submit(aggregate_one_run, run, args.bin_size, args.skip_existing)
                future_to_run[future] = run

            completed = 0
            for future in as_completed(future_to_run):
                completed += 1
                run = future_to_run[future]
                try:
                    run_id, status = future.result()
                    if status == "skipped":
                        print(
                            f"[{completed}/{len(runs)}] Skipping {run_id}: aggregated files already exist"
                        )
                    else:
                        print(f"[{completed}/{len(runs)}] Finished {run_id}")
                    succeeded += 1
                except Exception as exc:
                    failed += 1
                    print(f"[{completed}/{len(runs)}] Failed {run.run_id}: {exc}")
                    if args.fail_fast:
                        raise

    print(
        f"Finished aggregation in {root}. "
        f"Succeeded: {succeeded}, failed: {failed}, total: {len(runs)}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

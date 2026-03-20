#!/usr/bin/env python3
"""
Benchmark script for running mock-routing.sh with different configurations.
Executes sbatch with various THREADS and NUMA parameters.
"""

import subprocess
import argparse
import sys
from pathlib import Path


def run_benchmark(threads, numa_flag, run_number, dry_run=False):
    """
    Executes a single benchmark run.
    
    Args:
        threads: Number of threads (e.g. 1, 2, 4, ...)
        numa_flag: NUMA parameter ("" or "-XX:+UseNUMA")
        run_number: Run number (1-5)
        dry_run: If True, commands are only displayed, not executed
    """
    # Format NUMA parameter
    numa_param = f"NUMA={numa_flag}" if numa_flag else "NUMA="
    
    # Construct command
    cmd = f"sbatch mock-routing.sh THREADS={threads} {numa_param}"
    
    # Display status
    numa_status = "with NUMA" if numa_flag else "without NUMA"
    print(f"[Run {run_number}/5] Threads={threads}, {numa_status}: {cmd}")
    
    if dry_run:
        print(f"  -> DRY RUN: Command would be executed")
        return True
    
    try:
        # Execute command
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"  -> Success: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  -> ERROR: {e.stderr.strip()}", file=sys.stderr)
        return False


def main():
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Runs benchmarks with different thread and NUMA configurations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only shows which commands would be executed (without actual execution)"
    )
    parser.add_argument(
        "--working-dir",
        type=str,
        default=".",
        help="Working directory (default: current directory)"
    )
    
    args = parser.parse_args()
    
    # Thread configurations
    thread_configs = [1, 2, 4, 8, 16, 24, 48, 96, 192]
    
    # NUMA configurations
    numa_configs = ["", "-XX:+UseNUMA"]
    
    # Number of repetitions
    repetitions = 5
    
    # Change working directory
    working_dir = Path(args.working_dir)
    if not working_dir.exists():
        print(f"ERROR: Directory {working_dir} does not exist!", file=sys.stderr)
        sys.exit(1)
    
    # Change to working directory
    import os
    os.chdir(working_dir)
    
    # Display mode
    if args.dry_run:
        print("=" * 70)
        print("DRY RUN MODE - No commands will be actually executed")
        print("=" * 70)
    
    print(f"\nStarting benchmarks with:")
    print(f"  - Thread configurations: {thread_configs}")
    print(f"  - NUMA configurations: without NUMA, with NUMA")
    print(f"  - Repetitions per configuration: {repetitions}")
    print(f"  - Total: {len(thread_configs) * len(numa_configs) * repetitions} runs")
    print(f"  - Working directory: {working_dir.absolute()}")
    print()
    
    # Counters for statistics
    total_runs = 0
    successful_runs = 0
    failed_runs = 0
    
    # Iterate through all combinations
    for threads in thread_configs:
        for numa_flag in numa_configs:
            print(f"\n{'=' * 70}")
            numa_desc = "with NUMA" if numa_flag else "without NUMA"
            print(f"Configuration: {threads} threads, {numa_desc}")
            print(f"{'=' * 70}")
            
            for run in range(1, repetitions + 1):
                total_runs += 1
                success = run_benchmark(threads, numa_flag, run, args.dry_run)
                
                if success:
                    successful_runs += 1
                else:
                    failed_runs += 1
                    
    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total runs executed: {total_runs}")
    print(f"Successful: {successful_runs}")
    print(f"Failed: {failed_runs}")
    
    if args.dry_run:
        print("\nDRY RUN completed - no commands were actually executed")
    
    # Exit code based on success
    if failed_runs > 0 and not args.dry_run:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

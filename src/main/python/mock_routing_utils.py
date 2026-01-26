import pandas as pd
import numpy as np
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor


def find_all_profiling_files(base_dir, commit_hash):
    """
    Find all profiling CSV files in the directory structure.

    Directory structure:
    base_dir/
        routing-mock_routing<threads>/
            <git_commit_hash>/
                routing-profiling-<timestamp>.csv       (numa=False)
                routing-profiling-numa<timestamp>.csv   (numa=True)

    Args:
        base_dir: Base directory containing the routing-mock_routing folders
        commit_hash: Git commit hash to look for

    Returns:
        List of tuples: (filepath, threads, numa)
    """
    base_path = Path(base_dir)
    files = []

    # Pattern to match routing-mock_routing<threads> folders
    folder_pattern = re.compile(r'^routing-mock_routing(\d+)$')

    # Pattern to match profiling files
    # routing-profiling-numa<timestamp>.csv for numa=True
    # routing-profiling-<timestamp>.csv for numa=False
    numa_file_pattern = re.compile(r'^routing-profiling-numa\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv$')
    regular_file_pattern = re.compile(r'^routing-profiling-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv$')

    # Iterate through base directory
    for thread_folder in base_path.iterdir():
        if not thread_folder.is_dir():
            continue

        # Match routing-mock_routing<threads> pattern
        match = folder_pattern.match(thread_folder.name)
        if not match:
            continue

        threads = int(match.group(1))

        # Look for the specific commit hash folder
        commit_folder = thread_folder / commit_hash
        if not commit_folder.is_dir():
            continue

        # Iterate through files in commit folder
        for csv_file in commit_folder.iterdir():
            if not csv_file.is_file():
                continue

            filename = csv_file.name

            # Check if it's a numa file
            if numa_file_pattern.match(filename):
                files.append((str(csv_file), threads, True))
            elif regular_file_pattern.match(filename):
                files.append((str(csv_file), threads, False))

    return files


def process_single_file(filepath, threads, numa):
    """Process one CSV file and return aggregated data with experiment settings."""
    # Read in chunks to avoid memory spikes
    chunks = pd.read_csv(filepath, chunksize=100000)

    all_values = []
    for chunk in chunks:
        all_values.extend(chunk['duration_ns'].values)

    all_values = np.array(all_values)

    return {
        # Experiment settings
        'threads': threads,
        'numa': numa,

        # Statistics
        'count': len(all_values),
        'mean': np.mean(all_values),
        'std': np.std(all_values),
        'min': np.min(all_values),
        'max': np.max(all_values),
        'p50': np.percentile(all_values, 50),
        'p95': np.percentile(all_values, 95),
        'p99': np.percentile(all_values, 99),

        # For CDF - 1000 quantiles (4 KB per file)
        'quantile_values': np.percentile(all_values, np.linspace(0, 100, 1000)),

        # For KDE - sample 50k points (200 KB per file)
        'sample': np.random.choice(all_values, size=min(50000, len(all_values)), replace=False)
    }


def _process_file_wrapper(args):
    """Wrapper for parallel processing that unpacks arguments."""
    filepath, threads, numa = args
    print(f"Processing {filepath}")
    result = process_single_file(filepath, threads, numa)
    result['filepath'] = filepath
    return result


def process_all_files(base_dir, commit_hash, num_workers=10):
    """Find and process all profiling files in the directory structure.

    Args:
        base_dir: Base directory containing the routing-mock_routing folders
        commit_hash: Git commit hash to look for
        num_workers: Number of parallel workers (default: 10)
    """
    files = find_all_profiling_files(base_dir, commit_hash)

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(_process_file_wrapper, files))

    return results
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union, Any, NamedTuple

import pandas as pd
import pyarrow.parquet as pq

_RUN_RE = re.compile(
    r"^sim(?P<sim_cpus>\d+)_hor(?P<horizon>\d+)_w(?P<worker>\d+)_r(?P<router>\d+)_(?P<pct>\d+)pct$"
)
_PROCESS_RE = re.compile(r".*_process_(?P<process_id>\d+)\.parquet$")


@dataclass(frozen=True, slots=True)
class RunMeta:
    run_id: str
    path: Path
    sim_cpus: int
    horizon: int
    worker_threads: int
    router_threads: int
    pct: int


def _u128_le_from_bytes(value: Union[bytes, bytearray, memoryview]) -> int:
    b = bytes(value)
    if len(b) != 16:
        raise ValueError(f"Expected exactly 16 bytes for u128 field, got {len(b)} bytes.")
    return int.from_bytes(b, byteorder="little", signed=False)


def _extract_process_id(path: Path) -> int:
    m = _PROCESS_RE.match(path.name)
    if not m:
        raise ValueError(f"Cannot extract process_id from filename: {path.name}")
    return int(m.group("process_id"))


def _add_run_metadata(
        df: pd.DataFrame,
        run: RunMeta,
        process_id: int,
        source_path: Optional[Path],
        include_source_path: bool,
) -> pd.DataFrame:
    df = df.copy()
    df["run_id"] = run.run_id
    df["sim_cpus"] = pd.Series(run.sim_cpus, index=df.index, dtype="int64")
    df["horizon"] = pd.Series(run.horizon, index=df.index, dtype="int64")
    df["worker_threads"] = pd.Series(run.worker_threads, index=df.index, dtype="int64")
    df["router_threads"] = pd.Series(run.router_threads, index=df.index, dtype="int64")
    df["pct"] = pd.Series(run.pct, index=df.index, dtype="int64")
    df["process_id"] = pd.Series(process_id, index=df.index, dtype="int64")

    if include_source_path:
        df["source_path"] = str(source_path)

    return df


def discover_runs(root: Union[str, Path]) -> list[RunMeta]:
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(root)

    runs: list[RunMeta] = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        m = _RUN_RE.match(p.name)
        if not m:
            continue

        runs.append(
            RunMeta(
                run_id=p.name,
                path=p,
                sim_cpus=int(m.group("sim_cpus")),
                horizon=int(m.group("horizon")),
                worker_threads=int(m.group("worker")),
                router_threads=int(m.group("router")),
                pct=int(m.group("pct")),
            )
        )
    return runs


def _read_parquet(path: Path) -> pd.DataFrame:
    print("Reading parquet: ", path)
    table = pq.read_table(path)
    return table.to_pandas(types_mapper=None)


def _convert_u128_column(df: pd.DataFrame, raw: str, out: str) -> pd.DataFrame:
    if raw not in df.columns:
        raise KeyError(f"Missing required column '{raw}'")

    def conv(x: Any) -> int:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            raise ValueError(f"Null encountered in u128 column '{raw}'")
        return _u128_le_from_bytes(x)

    df = df.copy()
    df[out] = df[raw].map(conv)
    df.drop(columns=[raw], inplace=True)
    return df


def load_instrument(
        run: RunMeta,
        processes: Optional[Iterable[int]] = None,
        include_source_path: bool = False,
) -> pd.DataFrame:
    instr_dir = run.path / "instrument"
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    proc_filter = None if processes is None else set(int(p) for p in processes)
    frames: list[pd.DataFrame] = []

    for path in sorted(instr_dir.glob("instrument_process_*.parquet")):
        print(f"Reading instrument data from: {path}")
        pid = _extract_process_id(path)
        if proc_filter is not None and pid not in proc_filter:
            continue

        df = _read_parquet(path)
        df = _convert_u128_column(df, "timestamp", "timestamp_u128")

        df = _add_run_metadata(df, run, pid, path, include_source_path)

        df["target"] = df["target"].astype("string")
        df["func_name"] = df["func_name"].astype("string")
        df["sim_time"] = pd.to_numeric(df["sim_time"], errors="raise").astype("int64")
        df["rank"] = pd.to_numeric(df["rank"], errors="raise").astype("int64")
        df.loc[df["rank"] == -1, "rank"] = pid

        try:
            df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("int64")
        except Exception:
            df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("UInt64")

        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_routing(
        run: RunMeta,
        processes: Optional[Iterable[int]] = None,
        include_source_path: bool = False,
) -> pd.DataFrame:
    instr_dir = run.path / "instrument"
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    proc_filter = None if processes is None else set(int(p) for p in processes)
    frames: list[pd.DataFrame] = []

    for path in sorted(instr_dir.glob("routing_process_*.parquet")):
        print(f"Reading routing data from: {path}")
        pid = _extract_process_id(path)
        if proc_filter is not None and pid not in proc_filter:
            continue

        df = _read_parquet(path)
        df = _convert_u128_column(df, "timestamp", "timestamp_u128")
        df = _convert_u128_column(df, "request_uuid", "request_uuid_u128")

        df = _add_run_metadata(df, run, pid, path, include_source_path)

        for col in ("target", "func_name", "person_id", "mode"):
            df[col] = df[col].astype("string")

        df["sim_time"] = pd.to_numeric(df["sim_time"], errors="raise").astype("int64")
        df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("int64")

        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class LoadRunResult(NamedTuple):
    qsim: pd.DataFrame
    logic: pd.DataFrame


def load_run(
        run: RunMeta,
        processes: Optional[Iterable[int]] = None,
        include_source_path: bool = False,
) -> LoadRunResult:
    return LoadRunResult(
        qsim=load_instrument(run, processes, include_source_path),
        logic=load_routing(run, processes, include_source_path),
    )


def aggregate_instrument_timebins(
        run: RunMeta,
        bin_size: int = 20,
        processes: Optional[Iterable[int]] = None,
        include_source_path: bool = False,
        output: bool = True,
) -> pd.DataFrame:
    """
    Read every `instrument_process_*.parquet` file for `run`, assert that the set of columns
    (metadata fields) is identical across all files, then for each file group rows by
    `func_name` and time bins of length `bin_size` (sim_time bins: 0..bin_size-1, bin_size..2*bin_size-1, ...)
    and compute duration statistics: max, min, mean and average (average is provided as an alias to mean).

    The per-file aggregated results are appended into a single DataFrame which is returned.
    If `output_path` is provided, the result is written to parquet for fast reads by other Python programs.

    Parameters
    - run: RunMeta describing the run directory
    - bin_size: size of sim_time bins (default 20)
    - processes: optional iterable of allowed process ids (filters instrument files)
    - include_source_path: whether to include source_path column in metadata
    - output: optional to write aggregated parquet file

    Returns
    - pandas.DataFrame with columns: run_id, sim_cpus, horizon, worker_threads, router_threads, pct,
      process_id, func_name, bin, bin_start, bin_end, duration_min_ns, duration_max_ns, duration_mean_ns,
      duration_average_ns (alias of mean), and optionally source_path
    """
    instr_dir = run.path / "instrument"
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    proc_filter = None if processes is None else set(int(p) for p in processes)
    aggregated_frames: list[pd.DataFrame] = []

    # gather files
    files = sorted(instr_dir.glob("instrument_process_*.parquet"))
    if not files:
        return pd.DataFrame()

    # baseline column set from first file
    first_path = files[0]
    base_table = _read_parquet(first_path)
    base_cols = set(base_table.columns)

    for path in files:
        pid = _extract_process_id(path)
        if proc_filter is not None and pid not in proc_filter:
            continue

        print(f"Processing instrument file: {path}")
        df = _read_parquet(path)

        # Assert metadata fields (column names) are the same across files
        cols = set(df.columns)
        if cols != base_cols:
            # Provide clear error showing the difference
            only_in_this = sorted(cols - base_cols)
            missing_from_this = sorted(base_cols - cols)
            raise AssertionError(
                f"Column mismatch for {path.name}:\n"
                f"Only in this file: {only_in_this}\n"
                f"Missing from this file: {missing_from_this}"
            )

        # convert timestamp and duration fields similarly to load_instrument
        if "timestamp" in df.columns:
            try:
                df = _convert_u128_column(df, "timestamp", "timestamp_u128")
            except KeyError:
                pass

        # Ensure duration_ns exists and is numeric
        if "duration_ns" in df.columns:
            try:
                df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("int64")
            except Exception:
                df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("UInt64")
        else:
            raise KeyError(f"Missing required 'duration_ns' column in {path.name}")

        if "func_name" not in df.columns:
            raise KeyError(f"Missing required 'func_name' column in {path.name}")

        # normalize types that are used for grouping
        df["func_name"] = df["func_name"].astype("string")
        df["sim_time"] = pd.to_numeric(df["sim_time"], errors="raise").astype("int64")

        # compute bin index
        df["bin"] = (df["sim_time"] // int(bin_size)).astype("int64")
        # aggregate per func_name and bin
        agg = (
            df.groupby(["func_name", "bin"], dropna=False)["duration_ns"]
            .agg(duration_max_ns="max", duration_min_ns="min", duration_mean_ns="mean", duration_median_ns="median")
            .reset_index()
        )

        # add bin boundaries
        agg["bin_start"] = (agg["bin"] * int(bin_size)).astype("int64")
        agg["bin_end"] = (agg["bin"] * int(bin_size) + int(bin_size) - 1).astype("int64")

        # add run + process metadata
        agg = _add_run_metadata(agg, run, pid, path if include_source_path else None, include_source_path)

        # keep column ordering reasonable
        cols_order = [
            "run_id",
            "sim_cpus",
            "horizon",
            "worker_threads",
            "router_threads",
            "pct",
            "process_id",
            "func_name",
            "bin",
            "bin_start",
            "bin_end",
            "duration_min_ns",
            "duration_max_ns",
            "duration_mean_ns",
            "duration_median_ns",
        ]
        if include_source_path:
            cols_order.insert(7, "source_path")
        # ensure all requested columns exist
        existing_cols_order = [c for c in cols_order if c in agg.columns]
        agg = agg[existing_cols_order]

        aggregated_frames.append(agg)

    result = pd.concat(aggregated_frames, ignore_index=True) if aggregated_frames else pd.DataFrame()

    if output == True and not result.empty:
        outp = Path(instr_dir / "instrument_aggregated.parquet")
        print(f"Writing aggregated instrument timebins to: {outp}")
        # use parquet for fast reads by other python programs
        result.to_parquet(outp, index=False)

    return result


def read_aggregated_instrument(run: RunMeta) -> pd.DataFrame:
    """
    Read an aggregated instrument parquet for `run` if it exists; otherwise compute the
    aggregation on-the-fly by delegating to `aggregate_instrument_timebins` (without
    writing to disk) and return the resulting DataFrame.

    Behavior:
    - Looks for `instrument/instrument_aggregated.parquet` first, then any files matching
      `instrument/instrument_aggregated*.parquet`.
    - If a matching file is found, uses the module's `_read_parquet` helper to load it.
    - If no file is found, calls `aggregate_instrument_timebins` with `output_path=None`
      to compute the aggregation in memory and returns that DataFrame.

    - If no file is found, calls `aggregate_instrument_timebins` with `output_path=False`
    - run: RunMeta for the run whose instrument aggregation should be read/created

    Returns
    - pandas.DataFrame with the aggregated instrument data
    """
    instr_dir = run.path / "instrument"
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    # Primary expected path
    cand = instr_dir / "instrument_aggregated.parquet"
    if cand.exists():
        return _read_parquet(cand)

    # Fallback: any other matching aggregated parquet
    matches = sorted(instr_dir.glob("instrument_aggregated*.parquet"))
    if matches:
        return _read_parquet(matches[0])

    raise FileNotFoundError(f"No aggregated instrument parquet found for run at {run.path}")


def aggregate_routing(
        run: RunMeta,
        processes: Optional[Iterable[int]] = None,
        output: bool = True,
) -> pd.DataFrame:
    """
    Concatenate all `routing_process_*.parquet` files under `run.path / 'instrument'` into a
    single pandas DataFrame, add a `rank` column set to the originating process id for every row,
    and optionally write the result to a parquet file named `routing_aggregated.parquet` in the
    instrument directory (or to `output_path` if provided).

    Parameters
    - run: RunMeta pointing to the run directory
    - processes: optional iterable of process ids to include
    - output: optional to write aggregated parquet; if True write to
      run.path / 'instrument' / 'routing_aggregated.parquet'

    Returns
    - pandas.DataFrame with the concatenated routing rows. Original columns are preserved;
      an additional integer `rank` column (process_id) is appended.
    """
    instr_dir = run.path / "instrument"
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    proc_filter = None if processes is None else set(int(p) for p in processes)
    frames: list[pd.DataFrame] = []

    files = sorted(instr_dir.glob("routing_process_*.parquet"))
    if not files:
        return pd.DataFrame()

    # baseline columns from first file
    base_cols = None
    for path in files:
        pid = _extract_process_id(path)
        if proc_filter is not None and pid not in proc_filter:
            continue

        print(f"Reading routing file: {path}")
        df = _read_parquet(path)

        # On-disk columns should remain the same across files; assert that
        cols = set(df.columns)
        if base_cols is None:
            base_cols = cols
        else:
            if cols != base_cols:
                only_in_this = sorted(cols - base_cols)
                missing_from_this = sorted(base_cols - cols)
                raise AssertionError(
                    f"Column mismatch for {path.name}:\n"
                    f"Only in this file: {only_in_this}\n"
                    f"Missing from this file: {missing_from_this}"
                )

        # add rank column equal to process id
        df["rank"] = pd.Series(pid, index=df.index, dtype="int64")

        frames.append(df)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # determine output path
    if output and not result.empty:
        outp = instr_dir / "routing_aggregated.parquet"
        outp.parent.mkdir(parents=True, exist_ok=True)
        print(f"Writing aggregated routing to: {outp}")
        result.to_parquet(outp, index=False)

    return result

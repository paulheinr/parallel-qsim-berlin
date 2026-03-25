from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union, Any, Iterable, Optional

import pandas as pd
import pyarrow.parquet as pq

_RUN_FOLDER_RE = re.compile(
    r"^sim(?P<sim_thread_count>\d+)_hor(?P<horizon>\d+)_w(?P<worker>\d+)_r(?P<routing_threads>\d+)_(?P<pct>\d+)pct_(?P<kind>sim|server(?P<server_number>\d+))$"
)
_PROCESS_RE = re.compile(r".*_process_(?P<process_id>\d+)\.parquet$")
_ROUTING_PROFILE_COLUMNS = [
    "thread",
    "now",
    "departure_time",
    "from",
    "to",
    "start",
    "duration_ns",
    "travel_time_s",
    "request_id",
]


@dataclass(frozen=True, slots=True)
class ServerPath:
    server_number: int
    path: Path


@dataclass(frozen=True, slots=True)
class RunMeta:
    run_id: str
    sim_thread_count: int
    horizon: int
    worker: int
    routing_threads: int
    pct: int
    sim_path: Path
    server_paths: tuple[ServerPath, ...]

    @property
    def all_paths(self) -> tuple[Path, ...]:
        return (self.sim_path, *(server.path for server in self.server_paths))

    @property
    def instrument_path(self) -> Path:
        return self.sim_path / "instrument"


@dataclass(slots=True)
class _RunBuilder:
    sim_thread_count: int
    horizon: int
    worker: int
    routing_threads: int
    pct: int
    sim_path: Path | None = None
    server_paths: dict[int, Path] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return (
            f"sim{self.sim_thread_count}_hor{self.horizon}_w{self.worker}_"
            f"r{self.routing_threads}_{self.pct}pct"
        )

    def to_meta(self) -> RunMeta:
        if self.sim_path is None:
            raise ValueError(f"Run {self.run_id} is missing its sim folder.")

        return RunMeta(
            run_id=self.run_id,
            sim_thread_count=self.sim_thread_count,
            horizon=self.horizon,
            worker=self.worker,
            routing_threads=self.routing_threads,
            pct=self.pct,
            sim_path=self.sim_path,
            server_paths=tuple(
                ServerPath(server_number=server_number, path=path)
                for server_number, path in sorted(self.server_paths.items())
            ),
        )


def _u128_le_from_bytes(value: Union[bytes, bytearray, memoryview]) -> int:
    raw = bytes(value)
    if len(raw) != 16:
        raise ValueError(f"Expected exactly 16 bytes for u128 field, got {len(raw)} bytes.")
    return int.from_bytes(raw, byteorder="little", signed=False)


def _read_parquet(path: Path) -> pd.DataFrame:
    print("Reading parquet: ", path)
    table = pq.read_table(path)
    return table.to_pandas(types_mapper=None)


def _convert_u128_column(df: pd.DataFrame, raw: str, out: str) -> pd.DataFrame:
    if raw not in df.columns:
        raise KeyError(f"Missing required column '{raw}'")

    def conv(value: Any) -> int:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            raise ValueError(f"Null encountered in u128 column '{raw}'")
        return _u128_le_from_bytes(value)

    df = df.copy()
    df[out] = df[raw].map(conv)
    df.drop(columns=[raw], inplace=True)
    return df


def _extract_process_id(path: Path) -> int:
    match = _PROCESS_RE.match(path.name)
    if not match:
        raise ValueError(f"Cannot extract process_id from filename: {path.name}")
    return int(match.group("process_id"))


def _add_run_metadata(
        df: pd.DataFrame,
        run: RunMeta,
        process_id: int,
        source_path: Path | None,
        include_source_path: bool,
) -> pd.DataFrame:
    df = df.copy()
    df["run_id"] = run.run_id
    df["sim_thread_count"] = pd.Series(run.sim_thread_count, index=df.index, dtype="int64")
    df["horizon"] = pd.Series(run.horizon, index=df.index, dtype="int64")
    df["worker"] = pd.Series(run.worker, index=df.index, dtype="int64")
    df["routing_threads"] = pd.Series(run.routing_threads, index=df.index, dtype="int64")
    df["pct"] = pd.Series(run.pct, index=df.index, dtype="int64")
    df["process_id"] = pd.Series(process_id, index=df.index, dtype="int64")

    if include_source_path:
        df["source_path"] = str(source_path)

    return df


def discover(folder: str | Path) -> list[RunMeta]:
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    builders: dict[tuple[int, int, int, int, int], _RunBuilder] = {}

    for path in sorted(folder.iterdir()):
        if not path.is_dir():
            continue

        match = _RUN_FOLDER_RE.match(path.name)
        if not match:
            continue

        key = (
            int(match.group("sim_thread_count")),
            int(match.group("horizon")),
            int(match.group("worker")),
            int(match.group("routing_threads")),
            int(match.group("pct")),
        )
        builder = builders.setdefault(
            key,
            _RunBuilder(
                sim_thread_count=key[0],
                horizon=key[1],
                worker=key[2],
                routing_threads=key[3],
                pct=key[4],
            ),
        )

        if match.group("kind") == "sim":
            if builder.sim_path is not None:
                raise ValueError(f"Run {builder.run_id} has more than one sim folder.")
            builder.sim_path = path
            continue

        server_number = int(match.group("server_number"))
        if server_number in builder.server_paths:
            raise ValueError(
                f"Run {builder.run_id} has more than one server folder for server {server_number}."
            )
        builder.server_paths[server_number] = path

    return [builders[key].to_meta() for key in sorted(builders)]


def read_aggregated_routing(run: RunMeta) -> pd.DataFrame:
    """
    Read an aggregated routing parquet for `run`.

    The aggregated routing parquet is expected in the sim folder because that is the
    canonical folder for a discovered run in the new metadata model. If the aggregated
    parquet does not exist yet, it is created on demand by `aggregate_routing`.
    """
    instr_dir = run.instrument_path
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    cand = instr_dir / "routing_aggregated.parquet"
    if cand.exists():
        df = _read_parquet(cand)
    else:
        df = aggregate_routing(run, output=True)

    df = _convert_u128_column(df, "timestamp", "timestamp_u128")
    df = _convert_u128_column(df, "request_uuid", "request_uuid_u128")
    return df


def aggregate_routing(
        run: RunMeta,
        processes: Optional[Iterable[int]] = None,
        output: bool = True,
) -> pd.DataFrame:
    """
    Concatenate all `routing_process_*.parquet` files under the run's sim `instrument`
    folder into one DataFrame, add metadata columns, and optionally write the aggregated
    parquet back to that instrument folder.
    """
    instr_dir = run.instrument_path
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    proc_filter = None if processes is None else {int(process) for process in processes}
    frames: list[pd.DataFrame] = []

    files = sorted(instr_dir.glob("routing_process_*.parquet"))
    if not files:
        return pd.DataFrame()

    base_cols: set[str] | None = None
    for path in files:
        pid = _extract_process_id(path)
        if proc_filter is not None and pid not in proc_filter:
            continue

        print(f"Reading routing file: {path}")
        df = _read_parquet(path)

        cols = set(df.columns)
        if base_cols is None:
            base_cols = cols
        elif cols != base_cols:
            only_in_this = sorted(cols - base_cols)
            missing_from_this = sorted(base_cols - cols)
            raise AssertionError(
                f"Column mismatch for {path.name}:\n"
                f"Only in this file: {only_in_this}\n"
                f"Missing from this file: {missing_from_this}"
            )

        df["rank"] = pd.Series(pid, index=df.index, dtype="int64")
        df = _add_run_metadata(df, run, pid, path, False)
        frames.append(df)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if output and not result.empty:
        outp = instr_dir / "routing_aggregated.parquet"
        outp.parent.mkdir(parents=True, exist_ok=True)
        print(f"Writing aggregated routing to: {outp}")
        result.to_parquet(outp, index=False)

    return result


def aggregate_qsim(
        run: RunMeta,
        bin_size: int = 20,
        processes: Optional[Iterable[int]] = None,
        output: bool = True,
) -> pd.DataFrame:
    """
    Aggregate qsim instrument parquet files into time bins per target, function, and
    process. The aggregated parquet is written to the sim instrument folder when
    `output` is true.
    """
    instr_dir = run.instrument_path
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    proc_filter = None if processes is None else {int(process) for process in processes}
    aggregated_frames: list[pd.DataFrame] = []

    files = sorted(instr_dir.glob("instrument_process_*.parquet"))
    if not files:
        return pd.DataFrame()

    first_path = files[0]
    base_table = _read_parquet(first_path)
    base_cols = set(base_table.columns)

    for path in files:
        pid = _extract_process_id(path)
        if proc_filter is not None and pid not in proc_filter:
            continue

        print(f"Processing instrument file: {path}")
        df = _read_parquet(path)

        cols = set(df.columns)
        if cols != base_cols:
            only_in_this = sorted(cols - base_cols)
            missing_from_this = sorted(base_cols - cols)
            raise AssertionError(
                f"Column mismatch for {path.name}:\n"
                f"Only in this file: {only_in_this}\n"
                f"Missing from this file: {missing_from_this}"
            )

        if "timestamp" in df.columns:
            df = _convert_u128_column(df, "timestamp", "timestamp_u128")

        if "duration_ns" not in df.columns:
            raise KeyError(f"Missing required 'duration_ns' column in {path.name}")
        if "func_name" not in df.columns:
            raise KeyError(f"Missing required 'func_name' column in {path.name}")
        if "target" not in df.columns:
            raise KeyError(f"Missing required 'target' column in {path.name}")
        if "sim_time" not in df.columns:
            raise KeyError(f"Missing required 'sim_time' column in {path.name}")

        try:
            df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("int64")
        except Exception:
            df["duration_ns"] = pd.to_numeric(df["duration_ns"], errors="raise").astype("UInt64")

        df["func_name"] = df["func_name"].astype("string")
        df["target"] = df["target"].astype("string")
        df["sim_time"] = pd.to_numeric(df["sim_time"], errors="raise").astype("int64")

        df["bin"] = (df["sim_time"] // int(bin_size)).astype("int64")
        agg = (
            df.groupby(["target", "func_name", "bin"], dropna=False)["duration_ns"]
            .agg(
                duration_max_ns="max",
                duration_min_ns="min",
                duration_mean_ns="mean",
                duration_median_ns="median",
            )
            .reset_index()
        )

        agg["bin_start"] = (agg["bin"] * int(bin_size)).astype("int64")
        agg["bin_end"] = (agg["bin"] * int(bin_size) + int(bin_size) - 1).astype("int64")
        agg = _add_run_metadata(agg, run, pid, path, False)

        cols_order = [
            "run_id",
            "sim_thread_count",
            "horizon",
            "worker",
            "routing_threads",
            "pct",
            "process_id",
            "target",
            "func_name",
            "bin",
            "bin_start",
            "bin_end",
            "duration_min_ns",
            "duration_max_ns",
            "duration_mean_ns",
            "duration_median_ns",
        ]
        agg = agg[[column for column in cols_order if column in agg.columns]].copy()
        aggregated_frames.append(agg)

    result = pd.concat(aggregated_frames, ignore_index=True) if aggregated_frames else pd.DataFrame()

    if output and not result.empty:
        outp = instr_dir / "instrument_aggregated.parquet"
        outp.parent.mkdir(parents=True, exist_ok=True)
        print(f"Writing aggregated qsim to: {outp}")
        result.to_parquet(outp, index=False)

    return result


def read_aggregated_qsim(run: RunMeta) -> pd.DataFrame:
    instr_dir = run.instrument_path
    if not instr_dir.is_dir():
        raise FileNotFoundError(instr_dir)

    for candidate in (
            instr_dir / "instrument_aggregated.parquet",
            instr_dir / "qsim_aggregated.parquet",
    ):
        if candidate.exists():
            return _read_parquet(candidate)

    return aggregate_qsim(run, output=True)


def read_router(run: RunMeta, commit_hash: str) -> pd.DataFrame:
    if not run.server_paths:
        return pd.DataFrame(columns=[*_ROUTING_PROFILE_COLUMNS, "server_id"])

    frames: list[pd.DataFrame] = []

    for server in run.server_paths:
        routing_dir = server.path / "routing" / commit_hash
        if not routing_dir.is_dir():
            raise FileNotFoundError(routing_dir)

        csv_files = sorted(routing_dir.glob("routing-profiling-*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No routing profiling CSV found under {routing_dir}")

        # raise error if len(csv_files) != 1
        if len(csv_files) > 1:
            raise AssertionError("There are more CSV than expected.")

        for csv_file in csv_files:
            print(f"Reading routing profiling CSV: {csv_file}")
            df = pd.read_csv(csv_file)
            missing_columns = [column for column in _ROUTING_PROFILE_COLUMNS if column not in df.columns]
            if missing_columns:
                raise ValueError(
                    f"Routing profiling CSV {csv_file} is missing columns: {missing_columns}"
                )

            df = df[_ROUTING_PROFILE_COLUMNS].copy()
            df["server_id"] = pd.Series(server.server_number, index=df.index, dtype="int64")
            df['request_id_u128'] = df['request_id'].astype(object).apply(int)
            # drop request_id
            df.drop(columns=["request_id"], inplace=True)
            frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=[*_ROUTING_PROFILE_COLUMNS, "server_id"]
    )

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

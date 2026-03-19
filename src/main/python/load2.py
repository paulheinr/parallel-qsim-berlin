from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_RUN_FOLDER_RE = re.compile(
    r"^sim(?P<sim_thread_count>\d+)_hor(?P<horizon>\d+)_w(?P<worker>\d+)_r(?P<routing_threads>\d+)_(?P<pct>\d+)pct_(?P<kind>sim|server(?P<server_number>\d+))$"
)


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

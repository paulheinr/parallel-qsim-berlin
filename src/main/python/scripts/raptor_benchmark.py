#!/usr/bin/env python3
"""Summary of the raptor benchmark (step B6, scripts/raptor-benchmark/run.sh).

Reads the files of one run and writes summary.md next to them:

- routing time per variant (µs per request: per fork the median of its rounds, over the forks the median and the
  range) and the percentiles of the times per request,
- the ratio of each variant to base/schedule, with a 95 % bootstrap interval (forks, then rounds within a fork),
- #transfers of SwissRailRaptorData per variant, from the logs,
- the routes of each variant against base/schedule, and of branch/versioned against branch/option,
- snapshot 0 and the deltas of TimetableUpdateBenchmark, against the budget interval / RTR,
- the methods in which the routing spends its time, from the JFR profiles (run.sh with JFR=1; needs `jfr` of a JDK
  on the PATH).

Run in src/main/python:

    uv run --group analysis python scripts/raptor_benchmark.py ../../../output/benchmark/raptor/<name>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

REFERENCE = ("base", "schedule")
VARIANTS = [("base", "schedule"), ("branch", "schedule"), ("branch", "option"), ("branch", "versioned")]
COMPARISONS = [
    (("branch", "schedule"), REFERENCE),
    (("branch", "option"), REFERENCE),
    (("branch", "versioned"), REFERENCE),
    (("branch", "versioned"), ("branch", "option")),
]
TRANSFERS = re.compile(r"#transfers \(between routeStops\) = (\d+)")


def name(variant: tuple[str, str]) -> str:
    return "/".join(variant)


def table(header: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def load_rounds(run: Path) -> pd.DataFrame:
    rounds = pd.read_csv(run / "rounds.csv")
    rounds = rounds[rounds["measured"]].copy()
    rounds["us"] = rounds["total_ns"] / 1000 / rounds["requests"]
    return rounds


def rounds_of(rounds: pd.DataFrame, variant: tuple[str, str]) -> list[np.ndarray]:
    """The µs per request of each measured round, per fork."""
    selected = rounds[(rounds["label"] == variant[0]) & (rounds["variant"] == variant[1])]
    return [group["us"].to_numpy() for _, group in selected.groupby("fork")]


def statistic(forks: list[np.ndarray]) -> float:
    """Median over the forks of the median of their rounds."""
    return float(np.median([np.median(fork) for fork in forks]))


def bootstrap(forks: list[np.ndarray], rng: np.random.Generator) -> float:
    chosen = rng.integers(0, len(forks), len(forks))
    return statistic([rng.choice(forks[f], len(forks[f])) for f in chosen])


def timing(run: Path, rounds: pd.DataFrame, rng: np.random.Generator, samples: int) -> str:
    reference = rounds_of(rounds, REFERENCE)
    rows = []
    for variant in VARIANTS:
        forks = rounds_of(rounds, variant)
        if not forks:
            continue
        medians = [np.median(fork) for fork in forks]
        requests = pd.concat(
            pd.read_csv(file).set_index("trip_id")["median_ns"]
            for file in sorted(run.glob(f"requests-{variant[0]}-{variant[1]}-*.csv"))
        ).groupby(level=0).median() / 1000
        ratio = statistic(forks) / statistic(reference)
        draws = [bootstrap(forks, rng) / bootstrap(reference, rng) for _ in range(samples)]
        low, high = np.percentile(draws, [2.5, 97.5])
        rows.append([
            name(variant), len(forks), f"{statistic(forks):.0f}", f"{min(medians):.0f}–{max(medians):.0f}",
            f"{requests.quantile(0.5):.0f}", f"{requests.quantile(0.9):.0f}", f"{requests.quantile(0.99):.0f}",
            f"{ratio:.3f}", f"{low:.3f}–{high:.3f}",
        ])
    return table(
        ["variant", "forks", "µs/request", "range of forks", "p50", "p90", "p99", f"ratio to {name(REFERENCE)}",
         "95 % interval"],
        rows,
    )


def transfers(run: Path) -> str:
    rows = []
    for variant in VARIANTS:
        counts = set()
        for log in sorted(run.glob(f"log-{variant[0]}-{variant[1]}-*.txt")):
            counts.update(int(m) for m in TRANSFERS.findall(log.read_text(errors="replace")))
        if counts:
            rows.append([name(variant), ", ".join(str(c) for c in sorted(counts))])
    return table(["variant", "#transfers"], rows)


def load_routes(run: Path, variant: tuple[str, str]) -> pd.DataFrame | None:
    files = sorted(run.glob(f"routes-{variant[0]}-{variant[1]}-*.tsv"))
    if not files:
        return None
    first = pd.read_csv(files[0], sep="\t", dtype={"route": str}).set_index("trip_id")
    for other in files[1:]:
        if not pd.read_csv(other, sep="\t", dtype={"route": str}).set_index("trip_id").equals(first):
            raise ValueError(f"The routes of {name(variant)} differ between {files[0].name} and {other.name}")
    return first


def routes(run: Path) -> str:
    sections = []
    rows = []
    for variant, reference in COMPARISONS:
        a, b = load_routes(run, variant), load_routes(run, reference)
        if a is None or b is None:
            continue
        joined = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
        different = joined[joined["route_a"] != joined["route_b"]]
        both = different[(different["arrival_a"] >= 0) & (different["arrival_b"] >= 0)]
        later = int((both["arrival_a"] > both["arrival_b"]).sum())
        earlier = int((both["arrival_a"] < both["arrival_b"]).sum())
        rows.append([
            f"{name(variant)} vs {name(reference)}", len(joined), len(joined) - len(different), len(different), earlier, later,
            int((different["pt_legs_a"] != different["pt_legs_b"]).sum()),
        ])
        if len(different):
            examples = [
                f"- `{trip}`: {row['route_a']}\n  vs {row['route_b']}" for trip, row in different.head(10).iterrows()
            ]
            sections.append(f"Differences of {name(variant)} vs {name(reference)}, the first ones:\n\n" + "\n".join(examples))
    return "\n\n".join(
        [table(["comparison", "trips", "identical", "different", "arrives earlier", "arrives later",
                "other number of pt legs"], rows)] + sections
    )


def updates(run: Path) -> str:
    if not (run / "updates.csv").exists():
        return "No results of TimetableUpdateBenchmark."
    snapshot = json.loads((run / "snapshot0.json").read_text())
    deltas = pd.read_csv(run / "updates.csv")
    deltas = deltas[deltas["measured"]]
    budget = snapshot["budget_ns"] / 1000

    def us(column: str) -> list[str]:
        values = deltas[column] / 1000
        return [f"{values.median():.0f}", f"{values.quantile(0.95):.0f}", f"{values.max():.0f}"]

    text = (
        f"Snapshot 0: {snapshot['routes']} routes, {snapshot['departures']} departures "
        f"({snapshot.get('removed_routes', 0)} routes that run backwards removed), "
        f"{snapshot['message_bytes'] / 1e6:.1f} MB in messages (largest {snapshot['largest_message_bytes'] / 1e3:.0f} kB), "
        f"built in {snapshot['build_s']:.2f} s. Peak at {snapshot['peak'] // 3600:02d}:{snapshot['peak'] % 3600 // 60:02d} "
        f"with {snapshot['running_at_peak']} running departures.\n\n"
        f"{len(deltas)} measured deltas, every {snapshot['interval_s']} s: median {deltas['trips'].median():.0f} trip updates "
        f"({deltas['changed_stops'].median():.0f} stops), {deltas['message_bytes'].median() / 1e3:.0f} kB per message, "
        f"{deltas['version_bytes'].median() / 1e6:.2f} MB per version. Budget interval / RTR at RTR {snapshot['rtr']:.0f}: "
        f"{budget:.0f} µs.\n\n"
    )
    rows = [["parse and applyDelta (router path)"] + us("parse_and_apply_delta_ns")]
    if "parse_ns" in deltas.columns:
        rows += [["– parse", *us("parse_ns")], ["– applyDelta (conversion to seconds and apply)", *us("apply_delta_ns")]]
    rows.append(["apply alone"] + us("apply_ns"))
    text += table(["per delta, µs", "median", "p95", "max"], rows)
    if "parse_seconds_ns" not in deltas.columns:
        return text
    encodings = [("ns (schema)", "message_bytes", "parse_ns"), ("seconds", "message_bytes_seconds", "parse_seconds_ns"),
                 ("delay in seconds", "message_bytes_delay", "parse_delay_ns")]
    return text + "\n\nThe same deltas with other numbers in the time fields, only parsed:\n\n" + table(
        ["times as", "kB per message", "parse, µs: median", "p95", "max"],
        [[label, f"{deltas[size].median() / 1e3:.0f}", *us(parse)] for label, size, parse in encodings],
    )


ROUTING = "ch.sbb.matsim.routing.pt.raptor.SwissRailRaptor.calcRoute("
TIMETABLES = {"RaptorScheduleTimetable", "VersionedRaptorTimetable"}


def hot_methods(profile: Path) -> tuple[int, Counter]:
    """The samples of a JFR profile in which the routing runs, and how many of them each method is on top of the stack."""
    process = subprocess.Popen(
        ["jfr", "print", "--events", "jdk.ExecutionSample", "--stack-depth", "40", str(profile)],
        stdout=subprocess.PIPE, text=True,
    )
    samples = 0
    top = Counter()
    frames: list[str] = []
    in_stack = False
    for line in process.stdout:
        if line.strip() == "stackTrace = [":
            in_stack, frames = True, []
        elif in_stack and line.strip() == "]":
            in_stack = False
            if any(frame.startswith(ROUTING) for frame in frames):
                samples += 1
                # a frame is "package.Class.method(parameter types) line: n"; counted as Class.method
                top[".".join(frames[0].split("(")[0].split(".")[-2:])] += 1
        elif in_stack:
            frames.append(line.strip())
    if process.wait() != 0:
        raise RuntimeError(f"jfr print failed for {profile}")
    return samples, top


def profiles(run: Path, rounds: pd.DataFrame, methods: int = 15) -> str:
    files = sorted(run.glob("profile-*.jfr"))
    if not files:
        return "No JFR profiles."
    if shutil.which("jfr") is None:
        return "JFR profiles found, but no `jfr` on the PATH."
    per_variant = {}
    for variant in VARIANTS:
        profiled = [file for file in files if file.name.startswith(f"profile-{variant[0]}-{variant[1]}-")]
        if not profiled:
            continue
        samples, top = 0, Counter()
        for file in profiled:
            s, t = hot_methods(file)
            samples += s
            top += t
        if samples == 0:
            raise ValueError(f"No samples in calcRoute in the profiles of {name(variant)}")
        per_variant[variant] = (samples, top, statistic(rounds_of(rounds, variant)))
    hottest = Counter()
    for samples, top, _ in per_variant.values():
        for method, count in top.items():
            hottest[method] = max(hottest[method], count / samples)
    chosen = [method for method, _ in hottest.most_common(methods)]

    def us(variant: tuple[str, str], count: float) -> str:
        samples, _, per_request = per_variant[variant]
        return f"{count / samples * per_request:.0f}"

    rows = [["samples in calcRoute"] + [str(per_variant[v][0]) for v in per_variant]]
    rows.append(["µs per request (rounds of these runs)"] + [f"{per_variant[v][2]:.0f}" for v in per_variant])
    rows += [[f"`{method}`"] + [us(v, per_variant[v][1][method]) for v in per_variant] for method in chosen]
    rows.append(["timetable lookups (RaptorScheduleTimetable, VersionedRaptorTimetable)"] + [
        us(v, sum(count for method, count in per_variant[v][1].items() if method.split(".")[0] in TIMETABLES))
        for v in per_variant
    ])
    return (
        "Self time of the methods on top of the stack while routing (JFR samples whose stack contains "
        "`SwissRailRaptor.calcRoute`, inlined methods counted as their own), as µs per request: share of the samples times the "
        "µs per request of the same runs, which include the overhead of JFR.\n\n"
        + table(["method"] + [name(v) for v in per_variant], rows)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Summary of the raptor benchmark (step B6)")
    parser.add_argument("run", type=Path, help="Output directory of scripts/raptor-benchmark/run.sh")
    parser.add_argument("--bootstrap", type=int, default=2000, help="Number of bootstrap samples")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    run: Path = args.run
    rng = np.random.default_rng(args.seed)
    machine = (run / "machine.txt").read_text().strip() if (run / "machine.txt").exists() else ""
    rounds = load_rounds(run)
    summary = "\n\n".join([
        f"# Raptor benchmark {run.name}",
        "```\n" + machine + "\n```",
        "## Routing time",
        timing(run, rounds, rng, args.bootstrap),
        "## Transfers",
        transfers(run),
        "## Routes",
        routes(run),
        "## Snapshot 0 and deltas",
        updates(run),
        "## Profiles",
        profiles(run, rounds),
    ]) + "\n"
    (run / "summary.md").write_text(summary)
    print(summary)


if __name__ == "__main__":
    main()

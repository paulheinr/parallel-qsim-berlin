#!/usr/bin/env python3
import subprocess
from dataclasses import dataclass
from typing import List

# Path to your low-level slurm script
LOWLEVEL_SCRIPT = "run-routing.sh"   # adjust if the filename is different

# ----------------------------------------------------------------------
# Time limit heuristic
# ----------------------------------------------------------------------

MAX_CPUS = 192
BASE_TIME_MIN = 2    # base runtime (in minutes) measured for SIM_CPUS = MAX_CPUS
SAFETY_FACTOR = 2     # safety margin
THREADS_PER_ROUTING_NODE = 24  # max threads per routing node


def minutes_to_hhmmss(mins: int) -> str:
    hours = mins // 60
    rem = mins % 60
    return f"{hours:02d}:{rem:02d}:00"


def time_for_sim_cpus(sim_cpus: int, pct: int = 1) -> str:
    if sim_cpus <= 0:
        sim_cpus = 1

    # Very rough scaling: T ~ BASE * (MAX_CPUS / SIM_CPUS) * SAFETY
    t = 10 + BASE_TIME_MIN * MAX_CPUS * SAFETY_FACTOR * pct // sim_cpus

    # Cap at 4 hours (adjust if needed)
    t = min(t, 4 * 60)

    return minutes_to_hhmmss(t)


def calculate_num_nodes(router_threads: int) -> int:
    """Calculate total nodes needed: 1 client + ceil(router_threads / THREADS_PER_ROUTING_NODE) routing nodes."""
    num_routing_nodes = (router_threads + THREADS_PER_ROUTING_NODE - 1) // THREADS_PER_ROUTING_NODE
    return 1 + num_routing_nodes  # 1 client node + routing nodes


# ----------------------------------------------------------------------
# Job description
# ----------------------------------------------------------------------

@dataclass
class JobConfig:
    phase: str
    sim_cpus: int
    horizon: int
    worker_threads: int
    router_threads: int
    pct: int


def submit_job(cfg: JobConfig, dry_run: bool = False) -> None:
    """Submit a single job to Slurm using sbatch and the low-level script."""
    tlimit = time_for_sim_cpus(cfg.sim_cpus, cfg.pct)
    num_nodes = calculate_num_nodes(cfg.router_threads)
    num_routing_nodes = num_nodes - 1  # for display purposes

    cmd: List[str] = [
        "sbatch",
        f"--time={tlimit}",
        f"--nodes={num_nodes}",
        f"--ntasks={num_nodes}",
        f"--job-name=sim_{cfg.sim_cpus}_hor{cfg.horizon}_r{cfg.router_threads}_w{cfg.worker_threads}_pct{cfg.pct}",
        LOWLEVEL_SCRIPT,
        f"SIM_CPUS={cfg.sim_cpus}",
        f"HORIZON={cfg.horizon}",
        f"WORKER_THREADS={cfg.worker_threads}",
        f"ROUTER_THREADS={cfg.router_threads}",
        f"PCT={cfg.pct}"
    ]

    print("Submitting job:")
    print(f"  SIM_CPUS       = {cfg.sim_cpus}")
    print(f"  HORIZON        = {cfg.horizon}")
    print(f"  WORKER_THREADS = {cfg.worker_threads}")
    print(f"  ROUTER_THREADS = {cfg.router_threads}")
    print(f"  PCT            = {cfg.pct}")
    print(f"  num_nodes      = {num_nodes} (1 client + {num_routing_nodes} routing)")
    print(f"  time limit     = {tlimit}")
    print("  command        =", " ".join(cmd))
    print()

    if not dry_run:
        subprocess.run(cmd, check=True)


# ----------------------------------------------------------------------
# Phases
# ----------------------------------------------------------------------

def make_phase1_jobs(pct=1) -> List[JobConfig]:
    """
    Phase 1 - Strong scaling of the simulation.
    HORIZON=600, WORKER=4, ROUTER=192.
    """
    phase = "phase1_strong_scaling"
    horizon = 600
    worker = 4
    router = 192

    sim_values = [1, 2, 4, 8, 16, 32, 64, 128, 192]
    return [
        JobConfig(
            phase=phase,
            sim_cpus=sim,
            horizon=horizon,
            worker_threads=worker,
            router_threads=router,
            pct=pct
        )
        for sim in sim_values
    ]


def make_phase2_jobs(pct=1) -> List[JobConfig]:
    """
    Phase 2 - Horizon variation.
    Use 2-3 SIM_CPUS values that you found interesting in Phase 1.
    Here: example 8 and 64 (adjust after you saw Phase 1 results).
    """
    phase = "phase2_horizon"
    worker = 4
    router = 192

    # TODO: adjust these after Phase 1 results
    sim_values = [8, 64, 192]
    horizons = [200, 1800]

    jobs: List[JobConfig] = []
    for sim in sim_values:
        for horizon in horizons:
            jobs.append(
                JobConfig(
                    phase=phase,
                    sim_cpus=sim,
                    horizon=horizon,
                    worker_threads=worker,
                    router_threads=router,
                    pct=pct
                )
            )
    return jobs


def make_phase3a_jobs(pct=1) -> List[JobConfig]:
    """
    Phase 3a - Worker thread variation.
    Fix SIM_CPUS at the "knee" and vary WORKER_THREADS.
    Example: SIM_CPUS=64 (adjust after Phase 1).
    """
    phase = "phase3a_workers"
    sim = 64          # TODO: set to your actual knee point
    horizon = 600     # or the most stressful horizon from Phase 2
    router = 192

    worker_values = [1, 8]

    return [
        JobConfig(
            phase=phase,
            sim_cpus=sim,
            horizon=horizon,
            worker_threads=worker,
            router_threads=router,
            pct=pct
        )
        for worker in worker_values
    ]


def make_phase3b_jobs(pct=1) -> List[JobConfig]:
    """
    Phase 3b - Router thread variation.
    Use one low and one high SIM_CPUS value and vary ROUTER_THREADS.
    Example: SIM_CPUS=8 and 64 (adjust after Phase 1).
    """
    phase = "phase3b_router"
    horizon = 600
    worker = 4

    # TODO: adjust these after Phase 1 results
    sim_values = [8, 64, 192]
    router_values = [1, 24, 64]

    jobs: List[JobConfig] = []
    for sim in sim_values:
        for router_threads in router_values:
            jobs.append(
                JobConfig(
                    phase=phase,
                    sim_cpus=sim,
                    horizon=horizon,
                    worker_threads=worker,
                    router_threads=router_threads,
                    pct=pct
                )
            )
    return jobs


def make_test(pct=1) -> List[JobConfig]: 
    return [JobConfig(phase="test", sim_cpus=192, horizon=600, worker_threads=4, router_threads=int(24), pct=pct)]


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main(dry_run: bool = False, pct: int = 1) -> None:
    jobs: List[JobConfig] = []
    # jobs.extend(make_test(pct))
    jobs.extend(make_phase1_jobs(pct))
    # jobs.extend(make_phase2_jobs(pct))
    # jobs.extend(make_phase3a_jobs(pct))
    # jobs.extend(make_phase3b_jobs(pct))

    for cfg in jobs:
        submit_job(cfg, dry_run=dry_run)
    
    print()
    print(f"Total jobs to submit: {len(jobs)}")


if __name__ == "__main__":
    # Simple CLI: if you call `python submit_experiments.py --dry-run`
    # it will only print the sbatch commands without executing them.
    # Use --pct <value> to set the pct parameter (default: 1)
    import sys

    dry = "--dry" in sys.argv
    
    # Parse --pct argument
    pct = 1
    if "--pct" in sys.argv:
        try:
            pct_idx = sys.argv.index("--pct")
            if pct_idx + 1 < len(sys.argv):
                pct = int(sys.argv[pct_idx + 1])
        except (ValueError, IndexError):
            print("Error: --pct requires an integer value")
            sys.exit(1)
    
    main(dry_run=dry, pct=pct)
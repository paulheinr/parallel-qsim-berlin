"""Neighbors of the partitions in the networks of the runs.

    neighbors = load_neighbors(runs)                    # the networks of the runs, one row per partition
    neighbors = neighbors_of({96: path_96, 192: ...})  # any partitioned networks

Two partitions are neighbors if a link connects them, in either direction. In every time step, a partition sends a
message to each neighbor and waits for the messages of all of them, also without agents. The networks are those of
run.env (NETWORK), read from the local shared-svn checkout. Rust and DSim use the same network for the same number of
partitions.

With volumes (link_volumes), each partition also gets the vehicles per day on its links (column volume) from a MATSim
run of the scenario, as an estimate of its computational load with agents: every partition waits for its slowest
neighbor, so a partition with much more traffic than the others holds all of them up. METIS only balances the number
of links (vertex weight InLinkCount).

Up to matsim-rust e20838e, every link counts (column neighbors). Since the branch main-mode-neighbors (2026-10-21),
SimNetworkPartition::find_neighbors ignores links that allow modes but none of the main modes (column
neighbors_main_modes): in Berlin, these are the pt links (mode pt only, a quarter of all links), whose vehicles are
teleported. A partition whose links to other partitions all lack a main mode keeps them as neighbors.
"""
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from compression import zstd
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

SVN_ROOT = Path.home()  # local svn checkouts: ~/shared-svn, ~/public-svn, ~/runs-svn
# link volumes of the calibrated 1pct run of Berlin v7.1 in MATSim
VOLUMES_1PCT = (SVN_ROOT / "public-svn/matsim/scenarios/countries/de/berlin/berlin-v7.1/calibrated-1pct/output"
                / "berlin-v7.1-1pct.output_links.csv.gz")
# qsim.main_modes of input/v7.1/*.config.yml
MAIN_MODES = frozenset({"car", "freight", "truck", "bike"})


def network_path(run_dir: Path) -> Path:
    """The network of a run (NETWORK in run.env) in the local checkout: .../shared-svn/x -> ~/shared-svn/x."""
    network = re.search(r"^NETWORK=['\"]?([^'\"\n]+)", (run_dir / "run.env").read_text(), re.MULTILINE).group(1)
    return SVN_ROOT / "shared-svn" / network.split("/shared-svn/", 1)[1]


def link_volumes(links_csv: Path = VOLUMES_1PCT, columns=("vol_car", "vol_freight", "vol_truck")) -> dict[str, float]:
    """Vehicles per link and day of a MATSim run (output_links.csv.gz) by link id. MATSim also counts the transit
    vehicles on the pt links there (about half of the sum in Berlin), which matsim-rust teleports, so partition_neighbors
    only adds the volumes of links with a main mode."""
    df = pd.read_csv(links_csv, sep=";", usecols=["link", *columns], dtype={"link": str})
    return dict(zip(df["link"], df[list(columns)].sum(axis=1)))


def partition_neighbors(network: Path, parts: int, volumes: dict[str, float] | None = None,
                        main_modes=MAIN_MODES) -> pd.DataFrame:
    """One row per partition: the number of its neighbors over all links (neighbors) and as matsim-rust counts them
    since main-mode-neighbors (neighbors_main_modes), the links between it and other partitions (boundary_links), and
    its links with a main mode (links, a link belongs to the partition of its to node; METIS balances their number,
    vertex weight InLinkCount), and with volumes the vehicles per day on these links (volume)."""
    partition, links = {}, []
    with zstd.open(network) as f:
        for _, element in ET.iterparse(f):
            if element.tag == "node":
                partition[element.get("id")] = int(element.find("attributes/attribute[@name='partition']").text)
                element.clear()
            elif element.tag == "link":
                links.append((element.get("id"), element.get("from"), element.get("to"), element.get("modes", "")))
                element.clear()
    if max(partition.values()) >= parts:
        raise ValueError(f"{network.name} has partitions beyond {parts}")

    neighbors, main_mode_neighbors = defaultdict(set), defaultdict(set)
    boundary, main_mode_links, volume = defaultdict(int), defaultdict(int), defaultdict(float)
    for link, from_node, to_node, modes in links:
        a, b = partition[from_node], partition[to_node]
        modes = set(filter(None, modes.split(",")))
        carries_vehicles = not modes or bool(modes & main_modes)
        if carries_vehicles:
            main_mode_links[b] += 1
            if volumes:
                volume[b] += volumes.get(link, 0.)
        if a != b:
            neighbors[a].add(b)
            neighbors[b].add(a)
            boundary[a] += 1
            boundary[b] += 1
            if carries_vehicles:
                main_mode_neighbors[a].add(b)
                main_mode_neighbors[b].add(a)
    return pd.DataFrame({"parts": parts, "partition": range(parts),
                         "neighbors": [len(neighbors[p]) for p in range(parts)],
                         # as find_neighbors: all neighbors if none is reached by a link with a main mode
                         "neighbors_main_modes": [len(main_mode_neighbors[p]) or len(neighbors[p])
                                                  for p in range(parts)],
                         "boundary_links": [boundary[p] for p in range(parts)],
                         "links": [main_mode_links[p] for p in range(parts)],
                         **({"volume": [volume[p] for p in range(parts)]} if volumes else {})})


def neighbors_of(networks: dict[int, Path], volumes: dict[str, float] | None = None) -> pd.DataFrame:
    """partition_neighbors of a network per number of partitions, read in parallel, with the file names in setting
    (e.g. berlin-v7.1.network.metis.*.xml.zst, for plots.setting_note)."""
    parts = sorted(networks)
    with ProcessPoolExecutor() as pool:
        frames = pool.map(partition_neighbors, [networks[p] for p in parts], parts, [volumes] * len(parts))
    neighbors = pd.concat(frames, ignore_index=True)
    neighbors["setting"] = neighbors["parts"].map(lambda p: re.sub(r"\.\d+(?=\.xml)", ".*", networks[p].name))
    return neighbors


def load_neighbors(runs: pd.DataFrame) -> pd.DataFrame:
    """Neighbors per partition of the network of every number of partitions in runs (load.load_runs)."""
    networks = {}
    for run in runs.itertuples():
        network = network_path(run.path)
        if networks.setdefault(run.parts, network) != network:
            raise ValueError(f"Two networks with {run.parts} partitions: {networks[run.parts]}, {network}")
    return neighbors_of(networks)

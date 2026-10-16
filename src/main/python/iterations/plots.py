"""Figures of iterations-vs-dsim-2026 for the paper. Every function takes the tables from load.py and returns a figure.

    fig = rtr_vs_parts(rtr_summary(phases))
    save(fig, "rtr_vs_parts")
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox
from matplotlib.ticker import FixedLocator, LogLocator, NullFormatter, PercentFormatter


OUT_DIR = Path(__file__).resolve().parents[1] / "jupyter-notebooks/plots/iterations-vs-dsim"

FULL_WIDTH = 7.0  # inches, text width of a two-column paper
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e6e5e1"

# Three categorical hues (validated for all pairs, so lines may cross) and gray for the reference without agents.
# Shades of one hue were too close to tell 1, 3 and 10 % apart. Plots label the pct directly at the lines as well.
PCT_COLORS = {0: "#8a8984", 1: "#2a78d6", 3: "#eb6834", 10: "#1baf7a"}
PHASE_COLORS = {"mobsim": "#2a78d6", "scoring": "#eb6834", "replanning": "#1baf7a", "other": "#eda100"}
# Plot 2 leaves out other: in DSim it is the setup and teardown of the mobsim and the analyses at the end of an
# iteration, in rust (with run_mobsim_phase) it is about 0.
TIMED_PHASES = ["mobsim", "scoring", "replanning"]
# Engine colors (validated as pair), only where no pct or phase colors are in the same figure: the rust red is too
# close to the orange of 3 % and of scoring. Line style and marker distinguish the engines everywhere.
ENGINES = {"rust": {"label": "Rust", "color": "#e34948", "linestyle": "-", "marker": "o"},
           "dsim": {"label": "DSim (Java)", "color": "#4a3aa7", "linestyle": (0, (4, 2)), "marker": "s"}}
TITLE = {"fontsize": 9, "fontweight": "bold"}
PARTS_TICKS = [1, 2, 4, 8, 16, 32, 64, 128, 192]
NARROW_TICKS = [1, 2, 4, 8, 16, 32, 64, 192]  # 128 and 192 overlap in narrow panels

STYLE = {
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 7, "legend.frameon": False,
    "pdf.fonttype": 42, "ps.fonttype": 42,  # embed TrueType fonts
    "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": MUTED, "axes.labelcolor": TEXT,
    "axes.titlecolor": TEXT, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": TEXT,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
    "lines.linewidth": 1.0, "lines.markersize": 3,
    "savefig.bbox": "tight", "savefig.dpi": 300,
}


def pct_label(pct: int) -> str:
    return "0 % (no agents)" if pct == 0 else f"{pct} %"


def parts_axis(ax, label=True, ticks=PARTS_TICKS):
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:g}")
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlim(0.8, 240)
    if label:
        ax.set_xlabel("Partitions")


def compact(value: float) -> str:
    """Three significant digits with k/M, e.g. 32.5k, 9.02k, 4.73M."""
    for limit, suffix in ((1e6, "M"), (1e3, "k"), (1, "")):
        if value >= limit:
            scaled = value / limit
            return f"{scaled:.{max(0, 2 - int(np.floor(np.log10(scaled))))}f}{suffix}"
    return f"{value:.3g}"


# Labels are boxed: padding between text and frame, in points
_LABEL_FONTSIZE = 6.5
_LABEL_PAD = 0.3 * _LABEL_FONTSIZE

# Candidate positions of a label relative to its point: offset in points (outside the box padding), horizontal and
# vertical alignment
_LABEL_POSITIONS = [(dx * r + np.sign(dx) * _LABEL_PAD, dy * r + np.sign(dy) * _LABEL_PAD, ha, va) for r in (1, 1.6)
                    for dx, dy, ha, va in [(0, 7, "center", "bottom"), (0, -7, "center", "top"),
                                           (8, 0, "left", "center"), (-8, 0, "right", "center"),
                                           (6, 6, "left", "bottom"), (-6, 6, "right", "bottom"),
                                           (6, -6, "left", "top"), (-6, -6, "right", "top")]]


def label_points(ax, points: list[tuple[float, float, str, str]]):
    """Writes each text in a box framed in its color next to its point, at the candidate position that covers the
    fewest line segments, markers and other labels, preferring positions close to the point. The axis scales and limits
    must be final."""
    renderer = ax.figure.canvas.get_renderer()
    px = renderer.points_to_pixels(1)
    segments, markers = [], []
    for line in ax.get_lines():
        xy = ax.transData.transform(line.get_xydata())
        for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
            n = max(2, int(np.hypot(x1 - x0, y1 - y0) / 2))
            segments.append(np.column_stack([np.linspace(x0, x1, n), np.linspace(y0, y1, n)]))
        if line.get_marker() not in (None, "None", ""):
            r = (line.get_markersize() / 2 + 1) * px
            markers += [Bbox.from_extents(x - r, y - r, x + r, y + r) for x, y in xy]
    line_points = np.vstack(segments) if segments else np.empty((0, 2))
    labels = [t.get_window_extent(renderer) for t in ax.texts]
    frame = ax.get_window_extent(renderer)

    for x, y, text, color in points:
        anchor = ax.transData.transform((x, y))
        best = None
        for dx, dy, ha, va in _LABEL_POSITIONS:
            label = ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                                fontsize=_LABEL_FONTSIZE, color=TEXT,
                                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                                          edgecolor=color, linewidth=0.8))
            box = label.get_window_extent(renderer).padded((_LABEL_PAD + 0.4) * px)  # text + padding + frame
            inside = ((line_points[:, 0] >= box.x0) & (line_points[:, 0] <= box.x1)
                      & (line_points[:, 1] >= box.y0) & (line_points[:, 1] <= box.y1))
            cost = (inside.sum() + 30 * sum(box.overlaps(m) for m in markers)
                    + 1000 * sum(box.overlaps(t) for t in labels)
                    + 1000 * (box.x0 < frame.x0 or box.x1 > frame.x1 or box.y0 < frame.y0 or box.y1 > frame.y1)
                    + 2 * np.hypot(*(np.array([box.x0 + box.x1, box.y0 + box.y1]) / 2 - anchor)) / px)
            if best is None or cost < best[0]:
                if best is not None:
                    best[1].remove()
                best = (cost, label, box)
            else:
                label.remove()
        labels.append(best[2])


def maximum(g: pd.DataFrame) -> pd.Series:
    return g.loc[g["rtr"].idxmax()]


def log_y(ax, minor_grid=True):
    ax.set_yscale("log")
    ax.yaxis.set_minor_locator(LogLocator(subs=range(2, 10)))
    ax.yaxis.set_minor_formatter(NullFormatter())
    if minor_grid:
        ax.grid(which="minor", axis="y", color=GRID, linewidth=0.3)


def rtr_lines(ax, df: pd.DataFrame, label_last: bool = False) -> list[tuple[float, float, str, str]]:
    """Draws the real-time ratio of rust and DSim over the partitions (median, band: min-max) and marks the maximum of
    each line with a ring, with label_last also the value at the largest number of partitions. Returns the labels of
    the marked points to write with label_points."""
    labels = []
    for engine, style in ENGINES.items():
        g = df[df["engine"] == engine].sort_values("parts")
        if g.empty:
            continue
        color = style["color"]
        ax.fill_between(g["parts"], g["rtr_min"], g["rtr_max"], color=color, alpha=0.15, linewidth=0)
        ax.plot(g["parts"], g["rtr"], color=color, linestyle=style["linestyle"], marker=style["marker"],
                markeredgecolor="white", markeredgewidth=0.6)
        marked = [maximum(g)]
        if label_last and g.iloc[-1]["parts"] != marked[0]["parts"]:
            marked.append(g.iloc[-1])
        for point in marked:
            ax.plot(point["parts"], point["rtr"], marker="o", markersize=7, markerfacecolor="none",
                    markeredgecolor=color, markeredgewidth=0.8)
            labels.append((point["parts"], point["rtr"], compact(point["rtr"]), color))
    return labels


def rtr_axes(ax, pct: int, ylabel: bool = True):
    parts_axis(ax, ticks=NARROW_TICKS)
    log_y(ax, minor_grid=False)
    ax.margins(y=0.22)  # room for the labels
    ax.set_title(pct_label(pct), loc="left", **TITLE)
    if ylabel:
        ax.set_ylabel("RTR")


def engine_legend(fig):
    handles = [Line2D([], [], color=s["color"], linestyle=s["linestyle"], marker=s["marker"], label=s["label"])
               for s in ENGINES.values()]
    fig.legend(handles=handles, ncols=len(handles), loc="lower center", bbox_to_anchor=(0.5, 1.0), handlelength=2.6)


def rtr_no_agents(rtr: pd.DataFrame) -> plt.Figure:
    """Plot 1a: real-time ratio over the number of partitions without agents (0 %), rust and DSim. The maxima and the
    values at the largest number of partitions are marked and labeled."""
    df = rtr[rtr["scoring"] & ~rtr["events"] & (rtr["pct"] == 0)]
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(FULL_WIDTH / 2, 2.6))
        labels = rtr_lines(ax, df, label_last=True)
        rtr_axes(ax, 0)
        ax.set_xlim(right=560)  # room for the labels right of the last values
        engine_legend(fig)
        fig.tight_layout()
        label_points(ax, labels)
    return fig


def rtr_vs_parts(rtr: pd.DataFrame) -> plt.Figure:
    """Plot 1b: real-time ratio over the number of partitions, one panel per pct with agents (rust with scoring, DSim),
    all on the same y scale. The maximum of each line is marked and labeled."""
    df = rtr[rtr["scoring"] & ~rtr["events"] & (rtr["pct"] > 0)]
    pcts = sorted(df["pct"].unique())
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, len(pcts), figsize=(FULL_WIDTH, 2.6), sharex=True, sharey=True, squeeze=False)
        labels = {}
        for i, (ax, pct) in enumerate(zip(axes.flat, pcts)):
            labels[ax] = rtr_lines(ax, df[df["pct"] == pct])
            rtr_axes(ax, pct, ylabel=i == 0)
        axes[0, 0].set_xlim(right=380)  # room to center the labels of maxima at 192 partitions (x is shared)
        engine_legend(fig)
        fig.tight_layout(w_pad=1.5)
        for ax, points in labels.items():
            label_points(ax, points)
    return fig


def phase_lines(phases: pd.DataFrame) -> plt.Figure:
    """Plot 2: wall time of mobsim, scoring and replanning per iteration over the partitions,
    logarithmic, one panel per pct on one y axis. Color: phase; line style and marker: engine as in plot 1 (the engine
    colors are not used next to the phase colors). Values below 1 ms, the resolution of the DSim logfile, are left
    out."""
    df = phases[phases["scoring"] & ~phases["events"]]
    floor = 1e-3
    pcts = sorted(df["pct"].unique())
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, len(pcts), figsize=(FULL_WIDTH, 2.6), sharex=True, sharey=True, squeeze=False)
        for ax, pct in zip(axes.flat, pcts):
            for engine, style in ENGINES.items():
                values = (df[(df["pct"] == pct) & (df["engine"] == engine)]
                          .pivot_table(index="parts", columns="phase", values="seconds").sort_index())
                for phase in TIMED_PHASES:
                    line = values.get(phase, pd.Series(dtype=float))
                    line = line[line >= floor]
                    ax.plot(line.index, line, color=PHASE_COLORS[phase], linestyle=style["linestyle"],
                            marker=style["marker"], markeredgecolor="white", markeredgewidth=0.6)
            parts_axis(ax, ticks=[1, 4, 16, 64, 192])
            log_y(ax, minor_grid=False)
            ax.set_title(pct_label(pct), loc="left", **TITLE)
        axes[0, 0].set_ylabel("Seconds per iteration")

        handles = ([Line2D([], [], color=PHASE_COLORS[p], label=p.capitalize()) for p in TIMED_PHASES]
                   + [Line2D([], [], color=MUTED, linestyle=s["linestyle"], marker=s["marker"], label=s["label"])
                      for s in ENGINES.values()])
        fig.legend(handles=handles, ncols=len(handles), loc="lower center", bbox_to_anchor=(0.5, 1.0),
                   handlelength=2.6)
        fig.tight_layout(w_pad=1.0)
    return fig


def scoring_overhead(rtr: pd.DataFrame) -> plt.Figure:
    """Plot 3 (rust): real-time ratio of the mobsim with and without scoring, and the additional mobsim wall time due
    to scoring (= RTR without / RTR with scoring - 1, as the wall time is simulated time / RTR)."""
    rust = rtr[(rtr["engine"] == "rust") & ~rtr["events"]]
    pcts = sorted(set(rust.loc[rust["scoring"], "pct"]) & set(rust.loc[~rust["scoring"], "pct"]))
    rust = rust[rust["pct"].isin(pcts)]
    by_scoring = rust.pivot_table(index=["pct", "parts"], columns="scoring", values="rtr")
    overhead = (by_scoring[False] / by_scoring[True] - 1).rename("overhead").reset_index()

    with plt.rc_context(STYLE):
        fig, (left, right) = plt.subplots(1, 2, figsize=(FULL_WIDTH, 2.8))
        for (pct, scoring), g in rust.groupby(["pct", "scoring"]):
            g = g.sort_values("parts")
            left.plot(g["parts"], g["rtr"], color=PCT_COLORS[pct], linestyle="-" if scoring else (0, (1, 1.5)),
                      marker="o" if scoring else None, markeredgecolor="white", markeredgewidth=0.6)
        parts_axis(left, ticks=NARROW_TICKS)
        log_y(left, minor_grid=False)
        left.set_ylabel("RTR")
        left.set_title("RTR of the mobsim", loc="left", **TITLE)
        left.legend(handles=[Line2D([], [], color=MUTED, marker="o", label="Scoring on"),
                             Line2D([], [], color=MUTED, linestyle=(0, (1, 1.5)), label="Scoring off")],
                    loc="lower right", handlelength=2.6)

        for pct, g in overhead.groupby("pct"):
            g = g.sort_values("parts")
            right.plot(g["parts"], g["overhead"], color=PCT_COLORS[pct], marker="o", markeredgecolor="white",
                       markeredgewidth=0.6)
        parts_axis(right, ticks=NARROW_TICKS)
        right.axhline(0, color=MUTED, linewidth=0.8)
        right.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        right.set_ylabel("Additional mobsim wall time")
        right.set_title("Overhead of scoring in the mobsim", loc="left", **TITLE)

        handles = [Line2D([], [], color=PCT_COLORS[p], linewidth=2, label=pct_label(p)) for p in pcts]
        fig.legend(handles=handles, ncols=len(handles), loc="lower center", bbox_to_anchor=(0.5, 1.0))
        fig.tight_layout(w_pad=2)
    return fig


def save(fig: plt.Figure, name: str, out_dir: Path = OUT_DIR, formats=("pdf", "png")) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{name}.{fmt}" for fmt in formats]
    for path in paths:
        # the style is only active while the figure is created, so the save options are given here
        with plt.rc_context(STYLE):
            fig.savefig(path, bbox_inches="tight", dpi=300)
    return paths

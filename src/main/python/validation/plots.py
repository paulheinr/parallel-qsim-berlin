"""Figures of the traffic validation rust vs. DSim (Berlin v7.1). Every function takes trips tables of load.read_trips
(one per run) and returns a figure; the style is that of iterations.plots.

    rust, dsim = read_trips(rust_output), read_trips(dsim_output)
    fig = departures(rust, dsim)
    save(fig, "departures")

The functions compare a run `a` with a reference run `b`: by default a is rust and b is DSim.

Colors: figures with the engine colors (rust red, DSim violet) show the modes in separate panels; the one figure with
mode colors (departures) tells the runs apart by line style, as phase_lines in iterations.plots does. The mode
colors are the first six categorical slots of the dataviz palette (validated as adjacent pairs on white; violet and
red are left out, since they mean DSim and rust in the other figures), so truck and freight share one color there.
"""
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, LogLocator, NullFormatter, PercentFormatter

from iterations.plots import ENGINES, FULL_WIDTH, GRID, MUTED, STYLE, TEXT, TITLE
from iterations.plots import save as _save

OUT_DIR = Path(__file__).resolve().parents[1] / "jupyter-notebooks/plots/rust-vs-dsim-validation"

# Panel order of the modes (others follow alphabetically), and "all" for all trips
MODES = ["car", "pt", "walk", "bike", "ride", "truck", "freight"]
ALL = "all"
# Mode colors (departures only), slots 1-6 of the dataviz palette in this order. Modes not listed fold into "other".
MODE_GROUPS = {"car": "car", "pt": "pt", "walk": "walk", "bike": "bike", "ride": "ride", "truck": "truck, freight",
               "freight": "truck, freight"}
MODE_COLORS = {"car": "#2a78d6", "pt": "#eb6834", "walk": "#1baf7a", "bike": "#eda100", "ride": "#e87ba4",
               "truck, freight": "#008300", "other": "#8a8984"}
# Line styles of run a and reference b where the color shows something else (as rust and DSim in iterations.plots)
RUN_LINESTYLES = (ENGINES["rust"]["linestyle"], ENGINES["dsim"]["linestyle"])
# Sequential ramp for the hexbin counts: blue steps 250-700 of the dataviz palette, so that single trips stay visible
DENSITY = LinearSegmentedColormap.from_list(
    "density", ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
                "#0d366b"])
# Per column: axis title, unit of the axes, its size in seconds or meters, unit of the summary
COLUMNS = {"trav_time": ("Travel time", "min", 60, "s"),
           "traveled_distance": ("Traveled distance", "km", 1000, "m"),
           "dep_time": ("Departure time", "h", 3600, "s")}
SUMMARY_FONTSIZE = 6
# Every figure names its runs in small print below its lower right corner (see run_note). Turn off for the paper.
RUN_NOTE = True


def run_name(trips: pd.DataFrame) -> str:
    """Name of the run of a trips table (load.read_trips): the run directory, below runs-svn experiment/run_id."""
    if "run" in trips.attrs:
        return trips.attrs["run"]
    path = Path(trips.attrs.get("path", "?"))
    run_dir = path.parent.parent if path.parent.name == "output" else path.parent
    return f"{run_dir.parent.parent.name}/{run_dir.name}" if run_dir.parent.name == "runs" else run_dir.name


def run_note(fig, a: pd.DataFrame, b: pd.DataFrame, label_a: str, label_b: str):
    if RUN_NOTE:
        fig.text(1.0, 0.0, f"{label_a}: {run_name(a)}, {label_b}: {run_name(b)}", ha="right", va="top",
                 fontsize=5.5, color=MUTED, transform=fig.transFigure)


def ordered(modes) -> list[str]:
    """Modes in the order of MODES, others alphabetically after them."""
    present = set(modes)
    return [m for m in MODES if m in present] + sorted(present - set(MODES))


def modes_of(*trips: pd.DataFrame) -> list[str]:
    return ordered(set().union(*(set(t["main_mode"].dropna()) for t in trips)))


def mode_panels(n: int, ncols: int = 4, height: float = 1.9, **kwargs):
    """Figure with n panels in rows of ncols; unused panels are hidden."""
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(FULL_WIDTH, height * nrows), squeeze=False, **kwargs)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    return fig, list(axes.flat[:n])


def label_outer(axes: list, xlabel: str, ylabel: str, ncols: int = 4):
    """x label on the panels without a panel below, y label on the first column."""
    for i, ax in enumerate(axes):
        if i + ncols >= len(axes):
            ax.set_xlabel(xlabel)
        if i % ncols == 0:
            ax.set_ylabel(ylabel)


def summary_box(ax, text: str, loc: str = "upper left"):
    x, ha = (0.04, "left") if "left" in loc else (0.96, "right")
    y, va = (0.96, "top") if "upper" in loc else (0.04, "bottom")
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va, fontsize=SUMMARY_FONTSIZE, color=TEXT,
            linespacing=1.3, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=GRID, linewidth=0.5))


def panel_title(ax, title: str, summary: str):
    """Bold title with a summary in small print between it and the panel (where it covers no data)."""
    lines = summary.count("\n") + 1
    ax.set_title(title, loc="left", pad=4 + lines * 1.25 * SUMMARY_FONTSIZE, **TITLE)
    ax.annotate(summary, (0, 1), xycoords="axes fraction", xytext=(0, 3), textcoords="offset points", ha="left",
                va="bottom", fontsize=SUMMARY_FONTSIZE, color=MUTED, linespacing=1.25)


def number(value: float, unit: str) -> str:
    """Three significant digits, e.g. 182 s, 0.5 s, 1.23e+03 m -> 1230 m."""
    if not np.isfinite(value):
        return "-"
    return f"{value:.0f} {unit}" if abs(value) >= 100 else f"{value:.3g} {unit}"


# ---------------------------------------------------------------------------------------------------------------------
# Per-trip comparison

def join_trips(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Trips of both runs, joined on trip_id (inner join), with the columns of a and b suffixed _a and _b. `mode` is
    the main mode where both runs have the same, otherwise "changed"."""
    columns = ["trip_id", "person", "main_mode", "dep_time", "trav_time", "arr_time", "traveled_distance"]
    joined = a[columns].merge(b[columns].drop(columns="person"), on="trip_id", suffixes=("_a", "_b"))
    joined["mode"] = joined["main_mode_a"].where(joined["main_mode_a"] == joined["main_mode_b"], "changed")
    return joined


def agreement(a: pd.DataFrame, b: pd.DataFrame, columns=("trav_time", "traveled_distance", "dep_time")
              ) -> pd.DataFrame:
    """Per-trip agreement of run a with reference b, one row per column and mode (main mode in both runs; "all" for
    all common trips, also those whose main mode changed): number of trips, share with identical values, median and
    mean of a - b, median of |a - b| (seconds or meters), Pearson correlation. The attrs of the result count the trips
    only in a, only in b and those with another main mode."""
    joined = join_trips(a, b)
    rows = []
    for column in columns:
        diff = joined[f"{column}_a"] - joined[f"{column}_b"]
        for mode in modes_of(a, b) + [ALL]:
            selected = joined["mode"] == mode if mode != ALL else slice(None)
            d, g = diff[selected], joined[selected]
            if not len(d):
                continue
            rows.append({"column": column, "mode": mode, "trips": len(d), "identical": (d == 0).mean(),
                         "median_diff": d.median(), "mean_diff": d.mean(), "median_abs_diff": d.abs().median(),
                         "r": g[f"{column}_a"].corr(g[f"{column}_b"])})
    result = pd.DataFrame(rows)
    result.attrs.update(only_a=int((~a["trip_id"].isin(b["trip_id"])).sum()),
                        only_b=int((~b["trip_id"].isin(a["trip_id"])).sum()),
                        changed_mode=int((joined["mode"] == "changed").sum()), common=len(joined))
    return result


def log_extent(*values: pd.Series) -> tuple[float, float]:
    """log10 of the smallest positive and the largest value, padded a little."""
    positive = pd.concat([v[v > 0] for v in values])
    lo, hi = np.log10(positive.min()), np.log10(positive.max())
    pad = max(0.05 * (hi - lo), 0.1)
    return lo - pad, hi + pad


def log_ticks(axis):
    axis.set_major_locator(LogLocator(base=10))
    axis.set_minor_locator(LogLocator(base=10, subs=range(2, 10)))
    axis.set_major_formatter(lambda x, _: f"{x:g}")
    axis.set_minor_formatter(NullFormatter())


def trip_scatter(a: pd.DataFrame, b: pd.DataFrame, column: str = "trav_time", label_a: str = ENGINES["rust"]["label"],
                 label_b: str = ENGINES["dsim"]["label"], gridsize: int = 45) -> plt.Figure:
    """Plot 2: per trip, the value of `column` (trav_time or traveled_distance) in run a (y) over reference b (x),
    joined on trip_id: hexbins with a logarithmic color scale shared by all panels, the 1:1 line, one panel per mode
    (main mode in both runs) and one for all common trips. Both axes are logarithmic, so trips with 0 in a or b are
    not drawn; the summary (share of identical values, median |a - b|, Pearson r) counts them."""
    title, unit, scale, summary_unit = COLUMNS[column]
    joined = join_trips(a, b)
    stats = agreement(a, b, columns=(column,)).set_index("mode")
    modes = [m for m in modes_of(a, b) + [ALL] if m in stats.index]
    with plt.rc_context(STYLE):
        fig, axes = mode_panels(len(modes), height=1.95, layout="constrained")
        collections = []
        for ax, mode in zip(axes, modes):
            g = joined if mode == ALL else joined[joined["mode"] == mode]
            x, y = g[f"{column}_b"] / scale, g[f"{column}_a"] / scale
            shown = (x > 0) & (y > 0)
            lo, hi = log_extent(x, y)
            collections.append(ax.hexbin(x[shown], y[shown], xscale="log", yscale="log", gridsize=gridsize,
                                         extent=(lo, hi, lo, hi), mincnt=1, cmap=DENSITY, linewidths=0))
            ax.plot([10 ** lo, 10 ** hi], [10 ** lo, 10 ** hi], color=MUTED, linewidth=0.8, linestyle=(0, (4, 2)))
            ax.set_xlim(10 ** lo, 10 ** hi)
            ax.set_ylim(10 ** lo, 10 ** hi)
            ax.set_aspect("equal")
            log_ticks(ax.xaxis)
            log_ticks(ax.yaxis)
            ax.grid(False)
            s = stats.loc[mode]
            panel_title(ax, f"{mode} ({s['trips']:,.0f})", f"identical {s['identical']:.1%}, r = {s['r']:.4f}\n"
                                                           f"median |Δ| {number(s['median_abs_diff'], summary_unit)}")
        vmax = max(c.get_array().max() for c in collections)
        norm = LogNorm(vmin=1, vmax=vmax)
        for c in collections:
            c.set_norm(norm)
        label_outer(axes, f"{label_b} [{unit}]", f"{label_a} [{unit}]")
        bar = fig.colorbar(collections[0], ax=list(axes), shrink=0.6, aspect=25, pad=0.02)
        bar.set_label("Trips per hexagon")
        bar.outline.set_visible(False)
        fig.suptitle(f"{title} per trip", x=0.0, ha="left", **TITLE)
        run_note(fig, a, b, label_a, label_b)
    return fig


# ---------------------------------------------------------------------------------------------------------------------
# Departures over the day

def departures_per_hour(trips: pd.DataFrame, hours: int = 36) -> pd.DataFrame:
    """Departures per hour of the day (0..hours, later ones in the last hour) per mode group of MODE_GROUPS."""
    trips = trips.dropna(subset=["dep_time"])
    hour = (trips["dep_time"] // 3600).clip(upper=hours - 1).astype(int)
    group = trips["main_mode"].map(MODE_GROUPS).fillna("other")
    counts = pd.crosstab(hour, group).reindex(range(hours), fill_value=0)
    return counts[[g for g in MODE_COLORS if g in counts]]


def departures(a: pd.DataFrame, b: pd.DataFrame, label_a: str = ENGINES["rust"]["label"],
               label_b: str = ENGINES["dsim"]["label"], hours: int = 36) -> plt.Figure:
    """Plot 1: departures per hour over the day (0 to 36 h) per main mode, run a solid and reference b dashed (top),
    and the difference a - b (bottom). Color: mode (truck and freight share one); the engine colors are not used."""
    counts_a, counts_b = departures_per_hour(a, hours), departures_per_hour(b, hours)
    groups = [g for g in MODE_COLORS if g in counts_a or g in counts_b]
    counts_a, counts_b = (c.reindex(columns=groups, fill_value=0) for c in (counts_a, counts_b))
    centers = np.arange(hours) + 0.5
    with plt.rc_context(STYLE):
        fig, (top, bottom) = plt.subplots(2, 1, figsize=(FULL_WIDTH, 3.8), sharex=True,
                                          gridspec_kw={"height_ratios": [2, 1.2]})
        for group in groups:
            for counts, linestyle in zip((counts_a, counts_b), RUN_LINESTYLES):
                top.plot(centers, counts[group], color=MODE_COLORS[group], linestyle=linestyle)
            bottom.plot(centers, counts_a[group] - counts_b[group], color=MODE_COLORS[group])
        top.set_ylabel("Departures per hour")
        top.set_ylim(bottom=0)
        top.set_title("Departures per hour", loc="left", **TITLE)
        bottom.axhline(0, color=MUTED, linewidth=0.8, zorder=1.5)
        bottom.set_ylabel(f"{label_a} − {label_b}")
        bottom.set_title(f"Difference {label_a} − {label_b}", loc="left", **TITLE)
        bottom.set_xlim(0, hours)
        bottom.xaxis.set_major_locator(FixedLocator(range(0, hours + 1, 3)))
        bottom.set_xlabel("Departure time [h]")
        top.grid(axis="x", visible=False)
        bottom.grid(axis="x", visible=False)

        handles = ([Line2D([], [], color=MODE_COLORS[g], linewidth=2, label=g) for g in groups]
                   + [Line2D([], [], color=MUTED, linestyle=ls, label=label)
                      for ls, label in zip(RUN_LINESTYLES, (label_a, label_b))])
        fig.legend(handles=handles, ncols=len(handles), loc="lower center", bbox_to_anchor=(0.5, 1.0),
                   handlelength=2.6)
        fig.tight_layout(h_pad=1.0)
        run_note(fig, a, b, label_a, label_b)
    return fig


# ---------------------------------------------------------------------------------------------------------------------
# Distributions

def ks_distance(x: np.ndarray, y: np.ndarray) -> float:
    """Kolmogorov-Smirnov distance: largest vertical gap between the ECDFs of x and y."""
    x, y = np.sort(x), np.sort(y)
    grid = np.concatenate([x, y])
    return float(np.max(np.abs(np.searchsorted(x, grid, side="right") / len(x)
                               - np.searchsorted(y, grid, side="right") / len(y))))


def trav_time_ecdf(a: pd.DataFrame, b: pd.DataFrame, label_a: str = ENGINES["rust"]["label"],
                   label_b: str = ENGINES["dsim"]["label"]) -> plt.Figure:
    """Plot 3: distribution (ECDF) of the travel time per main mode, run a and reference b, one panel per mode and one
    for all trips, logarithmic travel time (trips of 0 s are counted in the share but not drawn). Each panel gives the
    difference of the medians and the Kolmogorov-Smirnov distance D. Colors and line styles: a as rust, b as DSim."""
    styles = (ENGINES["rust"], ENGINES["dsim"])
    modes = modes_of(a, b) + [ALL]
    with plt.rc_context(STYLE):
        fig, axes = mode_panels(len(modes), height=1.75, sharey=True)
        for ax, mode in zip(axes, modes):
            values = [(t if mode == ALL else t[t["main_mode"] == mode])["trav_time"].dropna().to_numpy() / 60
                      for t in (a, b)]
            for v, style in zip(values, styles):
                if len(v):
                    ax.ecdf(v, color=style["color"], linestyle=style["linestyle"])
            positive = np.concatenate([v[v > 0] for v in values])
            ax.set_xscale("log")
            ax.set_xlim(np.quantile(positive, 0.002) / 1.3, np.quantile(positive, 0.999) * 1.3)
            log_ticks(ax.xaxis)
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.set_title(mode, loc="left", **TITLE)
            if all(len(v) for v in values):
                delta = np.median(values[0]) - np.median(values[1])
                summary_box(ax, f"Δ median {delta * 60:+.0f} s\nD = {ks_distance(*values):.3f}")
        label_outer(axes, "Travel time [min]", "Share of trips")
        handles = [Line2D([], [], color=s["color"], linestyle=s["linestyle"], label=label)
                   for s, label in zip(styles, (label_a, label_b))]
        fig.legend(handles=handles, ncols=len(handles), loc="lower center", bbox_to_anchor=(0.5, 1.0),
                   handlelength=2.6)
        fig.tight_layout(w_pad=0.8, h_pad=1.0)
        run_note(fig, a, b, label_a, label_b)
    return fig


def save(fig: plt.Figure, name: str, out_dir: Path = OUT_DIR, formats=("pdf", "png")) -> list[Path]:
    return _save(fig, name, out_dir, formats)

"""Writes plots/index.html in runs-svn: one page with all figures of the validation, to scroll through them quickly.

    cd src/main/python && uv run --group analysis python -m validation.report

The page reads nothing itself; this module collects every comparison directory `plots/<a>_vs_<b>/` (written by
`python -m validation --experiment a --reference b`) with its agreement.csv and embeds the table as JSON. The figures
are linked relatively (PNG), so the page works from the svn checkout as long as it stays next to the directories.

Layout: one row per setting (pct, traffic and link dynamics, seed), one column per comparison (Rust vs. DSim, Rust vs.
QSim, DSim vs. QSim), one figure type at a time. Above, a matrix of the agreement (setting x comparison) for a chosen
column and mode. Experiments with another base name (e.g. it0 and it100) are separate groups.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .load import DATA_ROOT
from .plots import ENGINES

PLOTS_DIR = DATA_ROOT / "plots"
# Figure files of a pair (without extension) and their names on the page
FIGURES = {"departures": "Departures per hour", "scatter_trav_time": "Travel time per trip",
           "scatter_traveled_distance": "Distance per trip", "trav_time_ecdf": "Travel time distribution"}
ENGINE_ORDER = ["rust", "dsim", "qsim"]
# Columns of agreement.csv that go into the page
METRICS = ["rel_mean_diff", "mean_diff", "median_diff", "median_abs_diff", "r", "identical", "trips"]


def engine_of(experiment: str) -> tuple[str, str]:
    """Engine and base name of an experiment name: dsim-validation-it0 -> (dsim, validation-it0)."""
    for engine in ("dsim", "qsim"):
        if experiment.startswith(f"{engine}-"):
            return engine, experiment[len(engine) + 1:]
    return "rust", experiment


def comparisons(plots_dir: Path) -> list[dict]:
    """All comparison directories <a>_vs_<b> with an agreement.csv, ordered by base and engines."""
    found = []
    for directory in sorted(plots_dir.glob("*_vs_*")):
        if not (directory / "agreement.csv").exists():
            continue
        a, b = directory.name.split("_vs_", 1)
        (engine_a, base), (engine_b, _) = engine_of(a), engine_of(b)
        found.append({"dir": directory.name, "base": base, "a": engine_a, "b": engine_b,
                      "label": f"{ENGINES[engine_a]['label']} vs. {ENGINES[engine_b]['label']}"})
    return sorted(found, key=lambda c: (c["base"], ENGINE_ORDER.index(c["a"]), ENGINE_ORDER.index(c["b"])))


def collect(plots_dir: Path) -> dict:
    comps = comparisons(plots_dir)
    if not comps:
        raise SystemExit(f"No <a>_vs_<b>/agreement.csv in {plots_dir}")
    settings, rows = {}, []
    for comp in comps:
        table = pd.read_csv(plots_dir / comp["dir"] / "agreement.csv")
        only = {c: c for c in table.columns if c.startswith("only_")}
        for pair, g in table.groupby("pair", sort=False):
            first = g.iloc[0]
            key = (comp["base"], pair)
            settings[key] = {"base": comp["base"], "pair": pair, "pct": int(first["pct"]),
                             "traffic": first.get("traffic"), "link": first.get("link"),
                             "seed": None if pd.isna(first.get("seed", float("nan"))) else int(first["seed"])}
            comp.setdefault("only", {})[pair] = {c.removeprefix("only_"): int(first[c]) for c in only}
            for record in g[["column", "mode"] + METRICS].to_dict("records"):
                rows.append({"dir": comp["dir"], "pair": pair, **record})
    ordered = sorted(settings.values(), key=lambda s: (s["base"], s["pct"], str(s["traffic"]), str(s["link"]),
                                                       s["seed"] or 0))
    for comp in comps:
        comp["pairs"] = sorted(comp["only"])
    return {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "figures": FIGURES, "comparisons": comps,
            "settings": ordered, "rows": rows,
            "engines": {k: {"label": v["label"], "color": v["color"]} for k, v in ENGINES.items()}}


def write(plots_dir: Path = PLOTS_DIR) -> Path:
    data = json.dumps(collect(plots_dir), separators=(",", ":"), default=lambda v: None)
    path = plots_dir / "index.html"
    path.write_text(TEMPLATE.replace("__DATA__", data.replace("</", "<\\/")))
    return path


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validation figures</title>
<style>
:root {
  --bg: #f7f6f3; --surface: #ffffff; --ink: #1d1d1b; --ink-2: #55544f; --ink-3: #8a8984; --line: #e3e1db;
  --accent: #2a78d6; --neg: 42, 120, 214; --pos: 227, 73, 72; --shadow: 0 1px 2px rgba(0,0,0,.06);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --surface: #1f1f1d; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #8f8e86; --line: #34332f;
    --accent: #5598e7; --neg: 85, 152, 231; --pos: 230, 103, 103; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #161615; --surface: #1f1f1d; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #8f8e86; --line: #34332f;
  --accent: #5598e7; --neg: 85, 152, 231; --pos: 230, 103, 103; --shadow: none;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif; }
header.bar { position: sticky; top: 0; z-index: 10; background: color-mix(in srgb, var(--bg) 92%, transparent);
             backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
.bar-inner { max-width: 1800px; margin: 0 auto; padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 10px 18px;
             align-items: center; }
h1 { font-size: 16px; margin: 0 8px 0 0; font-weight: 650; letter-spacing: -.01em; }
.group { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.group > span { color: var(--ink-3); font-size: 12px; margin-right: 2px; }
button.chip { border: 1px solid var(--line); background: var(--surface); color: var(--ink-2); border-radius: 999px;
              padding: 3px 10px; font: inherit; font-size: 12.5px; cursor: pointer; }
button.chip[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }
button.chip:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
select { font: inherit; font-size: 12.5px; padding: 3px 6px; border-radius: 6px; border: 1px solid var(--line);
         background: var(--surface); color: var(--ink); }
main { max-width: 1800px; margin: 0 auto; padding: 16px; }
.meta { color: var(--ink-3); font-size: 12px; margin: 0 0 14px; }
section.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; box-shadow: var(--shadow);
               padding: 14px 16px; margin-bottom: 18px; }
section.card h2 { font-size: 14px; margin: 0 0 10px; font-weight: 650; }
.overview-controls { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
.table-wrap { overflow-x: auto; }
table.matrix { border-collapse: separate; border-spacing: 2px; font-variant-numeric: tabular-nums; font-size: 12.5px; }
table.matrix th { font-weight: 600; color: var(--ink-2); text-align: left; padding: 4px 8px; white-space: nowrap; }
table.matrix td { padding: 4px 10px; text-align: right; border-radius: 4px; white-space: nowrap; cursor: pointer; }
table.matrix tr:hover th { color: var(--ink); }
table.matrix td.na { color: var(--ink-3); cursor: default; }
.legend-note { color: var(--ink-3); font-size: 12px; margin-top: 8px; }
.grid-head { position: sticky; top: var(--bar-h, 56px); z-index: 5; background: var(--bg); padding: 8px 0 6px;
             display: grid; gap: 10px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
.grid-head div { font-weight: 650; font-size: 13px; }
.grid-head .eng { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin: 0 4px 0 6px; }
.setting { scroll-margin-top: calc(var(--bar-h, 56px) + 44px); margin-bottom: 20px; }
.setting h3 { font-size: 13.5px; margin: 0 0 6px; font-weight: 650; display: flex; gap: 10px; align-items: baseline; }
.setting h3 small { font-weight: 400; color: var(--ink-3); font-size: 12px; }
.row { display: grid; gap: 10px; }
figure { margin: 0; background: #fff; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
figure img { display: block; width: 100%; height: auto; cursor: zoom-in; }
figure figcaption { background: var(--surface); color: var(--ink-2); font-size: 12px; padding: 5px 8px;
                    border-top: 1px solid var(--line); display: flex; justify-content: space-between; gap: 8px;
                    font-variant-numeric: tabular-nums; }
figure.missing { display: grid; place-items: center; min-height: 120px; color: var(--ink-3); font-size: 12px;
                 background: var(--surface); }
.lightbox { position: fixed; inset: 0; background: rgba(10,10,10,.88); z-index: 50; display: none;
            flex-direction: column; align-items: center; justify-content: center; padding: 16px; }
.lightbox.open { display: flex; }
.lightbox img { max-width: 100%; max-height: calc(100vh - 70px); background: #fff; border-radius: 6px; }
.lightbox .cap { color: #f0efec; font-size: 13px; margin-top: 10px; text-align: center; }
.lightbox .hint { color: #a9a8a1; font-size: 11.5px; }
@media (max-width: 900px) { .row, .grid-head { grid-template-columns: 1fr !important; } .grid-head { display: none; } }
</style>
</head>
<body>
<header class="bar" id="bar"><div class="bar-inner">
  <h1>Validation figures</h1>
  <div class="group" id="bases"></div>
  <div class="group" id="figs"><span>Figure</span></div>
  <div class="group" id="comps"><span>Comparisons</span></div>
  <div class="group" id="filters"></div>
</div></header>
<main>
  <p class="meta" id="meta"></p>
  <section class="card">
    <h2>Agreement per setting</h2>
    <div class="overview-controls">
      <label>Column <select id="m-column"></select></label>
      <label>Mode <select id="m-mode"></select></label>
      <label>Value <select id="m-metric"></select></label>
    </div>
    <div class="table-wrap"><table class="matrix" id="matrix"></table></div>
    <p class="legend-note" id="matrix-note"></p>
  </section>
  <div class="grid-head" id="grid-head"></div>
  <div id="rows"></div>
</main>
<div class="lightbox" id="lightbox" role="dialog" aria-modal="true">
  <img id="lb-img" alt="">
  <div class="cap"><div id="lb-cap"></div><div class="hint">← → comparison · ↑ ↓ setting · 1–4 figure · Esc close</div></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const METRIC_LABELS = {rel_mean_diff: "Δ sum (a/b − 1)", mean_diff: "Δ mean", median_diff: "Δ median",
  median_abs_diff: "median |Δ|", r: "correlation r", identical: "identical share", trips: "trips"};
const UNITS = {trav_time: "s", traveled_distance: "m", dep_time: "s"};
const TRAFFIC = {kinematicWaves: "kinematic waves", queue: "queue", withHoles: "with holes"};
const store = {
  get(k, d) { try { const v = localStorage.getItem("validation-report:" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("validation-report:" + k, JSON.stringify(v)); } catch (e) {} }
};
const bases = [...new Set(D.comparisons.map(c => c.base))];
const state = {
  base: bases.includes(store.get("base")) ? store.get("base") : bases[0],
  fig: store.get("fig", Object.keys(D.figures)[0]),
  hidden: new Set(store.get("hidden", [])),
  filters: store.get("filters", {}),
  column: store.get("column", "trav_time"), mode: store.get("mode", "car"), metric: store.get("metric", "rel_mean_diff"),
};
if (!D.figures[state.fig]) state.fig = Object.keys(D.figures)[0];
const rowIndex = {};
for (const r of D.rows) rowIndex[`${r.dir}|${r.pair}|${r.column}|${r.mode}`] = r;

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k);
  return e;
}
function chip(label, pressed, onclick) {
  return el("button", {class: "chip", type: "button", "aria-pressed": String(pressed), onclick}, label);
}
const comps = () => D.comparisons.filter(c => c.base === state.base);
const visibleComps = () => comps().filter(c => !state.hidden.has(c.dir));
const settingLabel = s => [`${s.pct} %`, TRAFFIC[s.traffic] || s.traffic, s.link, s.seed != null ? `seed ${s.seed}` : null]
  .filter(Boolean).join(" · ");
function settings() {
  return D.settings.filter(s => s.base === state.base && ["pct", "traffic", "link", "seed"].every(k => {
    const f = state.filters[k]; return !f || !f.length || f.includes(String(s[k]));
  }));
}
function fmt(value, metric, column) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (metric === "rel_mean_diff") return `${value >= 0 ? "+" : "−"}${Math.abs(value * 100).toFixed(1)} %`;
  if (metric === "identical") return `${(value * 100).toFixed(1)} %`;
  if (metric === "r") return value.toFixed(3);
  if (metric === "trips") return value.toLocaleString("en");
  const sign = metric === "median_abs_diff" ? "" : (value >= 0 ? "+" : "−");
  return `${sign}${Math.round(Math.abs(value))} ${UNITS[column] || ""}`;
}
function tint(value, metric) {
  // diverging: blue below 0, red above, gray midpoint; only for signed differences
  if (value === null || value === undefined || !["rel_mean_diff", "mean_diff", "median_diff"].includes(metric)) return "";
  const scale = metric === "rel_mean_diff" ? 0.10 : 120;
  const t = Math.min(Math.abs(value) / scale, 1);
  return `background: rgba(${getComputedStyle(document.documentElement).getPropertyValue(value < 0 ? "--neg" : "--pos")}, ${(0.08 + 0.5 * t).toFixed(2)})`;
}

function renderBar() {
  const b = document.getElementById("bases"); b.replaceChildren();
  if (bases.length > 1) {
    b.append(el("span", {}, "Experiment"));
    for (const base of bases) b.append(chip(base, base === state.base, () => { state.base = base; store.set("base", base); render(); }));
  }
  const f = document.getElementById("figs"); f.replaceChildren(el("span", {}, "Figure"));
  Object.entries(D.figures).forEach(([key, label], i) =>
    f.append(chip(`${i + 1} ${label}`, key === state.fig, () => setFig(key))));
  const c = document.getElementById("comps"); c.replaceChildren(el("span", {}, "Comparisons"));
  for (const comp of comps()) c.append(chip(comp.label, !state.hidden.has(comp.dir), () => {
    state.hidden.has(comp.dir) ? state.hidden.delete(comp.dir) : state.hidden.add(comp.dir);
    if (!visibleComps().length) state.hidden.delete(comp.dir);
    store.set("hidden", [...state.hidden]); render();
  }));
  const fl = document.getElementById("filters"); fl.replaceChildren();
  const all = D.settings.filter(s => s.base === state.base);
  for (const [key, label] of [["pct", "pct"], ["traffic", "Traffic"], ["link", "Link"], ["seed", "Seed"]]) {
    const values = [...new Set(all.map(s => s[key]).filter(v => v !== null && v !== undefined).map(String))];
    if (values.length < 2) continue;
    if (key === "pct") values.sort((x, y) => x - y);
    const g = el("div", {class: "group"}, el("span", {}, label));
    for (const v of values) {
      const on = (state.filters[key] || []).includes(v);
      g.append(chip(key === "pct" ? `${v} %` : (TRAFFIC[v] || v), on, () => {
        const cur = new Set(state.filters[key] || []); on ? cur.delete(v) : cur.add(v);
        state.filters[key] = [...cur]; store.set("filters", state.filters); render();
      }));
    }
    fl.append(g);
  }
  document.documentElement.style.setProperty("--bar-h", document.getElementById("bar").offsetHeight + "px");
}

function renderOverview() {
  const columns = [...new Set(D.rows.map(r => r.column))], modes = [...new Set(D.rows.map(r => r.mode))];
  const order = ["car", "pt", "walk", "bike", "ride", "truck", "freight", "all"];
  modes.sort((a, b) => (order.indexOf(a) + 99) % 108 - (order.indexOf(b) + 99) % 108 || a.localeCompare(b));
  const fill = (id, values, labels, key) => {
    const s = document.getElementById(id); s.replaceChildren();
    for (const v of values) s.append(el("option", {value: v}, labels ? labels[v] : v));
    s.value = values.includes(state[key]) ? state[key] : values[0]; state[key] = s.value;
    s.onchange = () => { state[key] = s.value; store.set(key, s.value); renderOverview(); };
  };
  fill("m-column", columns, null, "column"); fill("m-mode", modes, null, "mode");
  fill("m-metric", Object.keys(METRIC_LABELS), METRIC_LABELS, "metric");
  const t = document.getElementById("matrix"); t.replaceChildren();
  const cs = comps();
  t.append(el("tr", {}, el("th", {}, "Setting"), ...cs.map(c => el("th", {}, c.label))));
  for (const s of settings()) {
    const tr = el("tr", {}, el("th", {}, settingLabel(s)));
    for (const c of cs) {
      const r = rowIndex[`${c.dir}|${s.pair}|${state.column}|${state.mode}`];
      const v = r ? r[state.metric] : null;
      const td = el("td", {class: r ? "" : "na", style: tint(v, state.metric), title: r ? `${c.label}, ${r.trips.toLocaleString("en")} trips` : ""},
        fmt(v, state.metric, state.column));
      if (r) td.addEventListener("click", () => { if (state.hidden.has(c.dir)) { state.hidden.delete(c.dir); render(); }
        document.getElementById(`s-${s.pair}`)?.scrollIntoView({behavior: "smooth"}); });
      tr.append(td);
    }
    t.append(tr);
  }
  document.getElementById("matrix-note").textContent =
    `a − b of ${state.column} for mode "${state.mode}"; a is the first engine of the comparison. ` +
    (["rel_mean_diff", "mean_diff", "median_diff"].includes(state.metric) ? "Blue: a lower, red: a higher. " : "") +
    "Click a cell to jump to the figures.";
}

function renderRows() {
  const vc = visibleComps(), cols = `repeat(${vc.length}, minmax(0, 1fr))`;
  const head = document.getElementById("grid-head");
  head.style.gridTemplateColumns = cols;
  head.replaceChildren(...vc.map(c => el("div", {},
    el("span", {class: "eng", style: `background:${D.engines[c.a].color}`}), D.engines[c.a].label, " vs. ",
    el("span", {class: "eng", style: `background:${D.engines[c.b].color}`}), D.engines[c.b].label)));
  const rows = document.getElementById("rows"); rows.replaceChildren();
  for (const s of settings()) {
    const car = vc.map(c => rowIndex[`${c.dir}|${s.pair}|trav_time|car`]);
    const row = el("div", {class: "row", style: `grid-template-columns:${cols}`});
    vc.forEach((c, i) => {
      if (!c.pairs.includes(s.pair)) { row.append(el("figure", {class: "missing"}, "no run")); return; }
      const src = `${c.dir}/${s.pair}/${state.fig}.png`;
      const only = c.only[s.pair] || {};
      const img = el("img", {src, loading: "lazy", alt: `${D.figures[state.fig]}, ${c.label}, ${settingLabel(s)}`,
        onclick: () => openLightbox(s.pair, c.dir)});
      img.onerror = () => img.replaceWith(el("div", {class: "missing", style: "padding:40px;text-align:center;color:var(--ink-3)"}, `missing: ${src}`));
      row.append(el("figure", {}, img, el("figcaption", {},
        el("span", {}, c.label),
        el("span", {}, car[i] ? `car Δ ${fmt(car[i].rel_mean_diff, "rel_mean_diff")}, median ${fmt(car[i].median_diff, "median_diff", "trav_time")}` : ""),
        el("span", {title: "trips only in a / only in b"}, Object.entries(only).map(([e, n]) => `only ${D.engines[e]?.label.split(" ")[0] || e} ${n}`).join(", ")))));
    });
    rows.append(el("div", {class: "setting", id: `s-${s.pair}`}, el("h3", {}, settingLabel(s), el("small", {}, s.pair)), row));
  }
}

function setFig(key) { state.fig = key; store.set("fig", key); renderBar(); renderRows(); if (lb.open) showLightbox(); }
function render() { renderBar(); renderOverview(); renderRows(); }

const lb = {open: false, pair: null, dir: null};
function openLightbox(pair, dir) { Object.assign(lb, {open: true, pair, dir}); showLightbox(); }
function showLightbox() {
  const s = settings().find(x => x.pair === lb.pair), c = D.comparisons.find(x => x.dir === lb.dir);
  document.getElementById("lb-img").src = `${lb.dir}/${lb.pair}/${state.fig}.png`;
  document.getElementById("lb-cap").textContent = `${D.figures[state.fig]} · ${c.label} · ${s ? settingLabel(s) : lb.pair}`;
  document.getElementById("lightbox").classList.add("open");
}
function closeLightbox() { lb.open = false; document.getElementById("lightbox").classList.remove("open"); }
document.getElementById("lightbox").addEventListener("click", e => { if (e.target.id === "lightbox") closeLightbox(); });
document.addEventListener("keydown", e => {
  const figKeys = Object.keys(D.figures);
  if (/^[1-9]$/.test(e.key) && figKeys[+e.key - 1] && !e.target.closest("select")) { setFig(figKeys[+e.key - 1]); return; }
  if (!lb.open) return;
  const vc = visibleComps().map(c => c.dir), ss = settings().map(s => s.pair);
  if (e.key === "Escape") closeLightbox();
  else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    lb.dir = vc[(vc.indexOf(lb.dir) + (e.key === "ArrowRight" ? 1 : vc.length - 1)) % vc.length]; showLightbox();
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    lb.pair = ss[(ss.indexOf(lb.pair) + (e.key === "ArrowDown" ? 1 : ss.length - 1)) % ss.length]; showLightbox();
  } else return;
  e.preventDefault();
});
document.getElementById("meta").textContent =
  `${D.comparisons.length} comparisons, generated ${D.generated} by python -m validation.report. ` +
  "Click a figure to enlarge it; keys 1–4 switch the figure type.";
window.addEventListener("resize", () => document.documentElement.style.setProperty("--bar-h", document.getElementById("bar").offsetHeight + "px"));
render();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plots", type=Path, default=PLOTS_DIR, help="directory with the <a>_vs_<b> directories")
    args = parser.parse_args()
    print(f"Written {write(args.plots)}")


if __name__ == "__main__":
    main()

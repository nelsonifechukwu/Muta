#!/usr/bin/env python3
"""Render benchmark sweep plots (bench/.runs/*.jsonl -> bench/plots/*.png).

Palette and mark rules follow the dataviz reference instance: categorical hues in
fixed order by MODE, direct value labels (relief for low-contrast fills), one axis
per chart, recessive grid, text in ink tokens rather than series colors.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "bench/.runs"
PLOTS = ROOT / "bench/plots"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e5e4e0"

MODE_COLOR = {          # fixed categorical order: blue, orange, aqua, yellow + neutral
    "router": "#2a78d6",
    "codraft": "#eb6834",
    "verify": "#1baf7a",
    "random": "#eda100",
    "baseline": "#8a887f",
}
BUNDLE_COLOR = {"muta-duo.gguf": "#2a78d6", "muta-duo-q.gguf": "#eb6834"}
BUNDLE_LABEL = {"muta-duo.gguf": "SmolLM2 front", "muta-duo-q.gguf": "Qwen0.8B front"}

MODE_ORDER = ["baseline", "router", "codraft", "random", "verify"]


def mode_of(config: str) -> str:
    name = config.split("/", 1)[1]
    if "alone" in name:
        return "baseline"
    return name.split("-")[0]


def load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)


def bar_panels(recs, value_key, xlabel, fname, max_key=None, unit=""):
    bundles = ["muta-duo.gguf", "muta-duo-q.gguf"]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.2), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, bundle in zip(axes, bundles):
        rows = [r for r in recs if r["bundle"] == bundle and r.get(value_key) is not None]
        rows += [r for r in recs if r["config"].startswith("shared/") and r.get(value_key) is not None] if bundle == bundles[0] else []
        rows.sort(key=lambda r: (MODE_ORDER.index(mode_of(r["config"])), r[value_key]))
        names = [r["config"].split("/", 1)[1] for r in rows]
        vals = [r[value_key] for r in rows]
        colors = [MODE_COLOR[mode_of(r["config"])] for r in rows]
        y = range(len(rows))
        ax.barh(y, vals, height=0.62, color=colors, zorder=3)
        if max_key:
            mx = [r.get(max_key) or 0 for r in rows]
            ax.plot(mx, y, "o", color=INK, markersize=4.5, zorder=4, linestyle="none")
        for i, v in enumerate(vals):
            ax.text(v, i, f" {v:,.0f}{unit}", va="center", ha="left", fontsize=7.5, color=INK, zorder=5)
        ax.set_yticks(list(y), names, fontsize=8, color=INK)
        ax.set_title(BUNDLE_LABEL[bundle], fontsize=10, color=INK, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.7, zorder=0)
        style_axes(ax)
        ax.margins(x=0.14)
    axes[0].set_xlabel(xlabel, fontsize=9, color=INK2)
    axes[1].set_xlabel(xlabel, fontsize=9, color=INK2)
    if max_key:
        fig.suptitle(f"{xlabel} by configuration - bar = session average, dot = fastest turn", fontsize=11, color=INK, x=0.01, ha="left")
    else:
        fig.suptitle(f"{xlabel} by configuration", fontsize=11, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(PLOTS / fname, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def pareto(acc_recs, perf_recs, fname):
    perf = {r["config"]: r for r in perf_recs}
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    fig.patch.set_facecolor(SURFACE)
    # stagger labels so the dense mid-cluster stays readable
    offsets = {"smol/router-t0": (-8, -16), "qwen/router-t0": (7, 4),
               "smol/codraft-f50": (-8, 14), "qwen/codraft-f50": (-58, 6),
               "shared/expert-alone": (10, -14), "smol/verify-t0": (7, -16),
               "qwen/verify-t0": (7, 5)}
    for r in acc_recs:
        p = perf.get(r["config"])
        if not p or not p.get("avg_tok_s"):
            continue
        shared = r["config"].startswith("shared/")
        color = "#52514e" if shared else BUNDLE_COLOR[r["bundle"]]
        ax.plot(p["avg_tok_s"], r["accuracy"], "o", color=color, markersize=9,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
        ax.annotate(r["config"].split("/", 1)[1] + (" (4B)" if shared else ""),
                    (p["avg_tok_s"], r["accuracy"]), textcoords="offset points",
                    xytext=offsets.get(r["config"], (7, 5)), fontsize=8, color=INK)
    ax.set_xscale("log", base=2)
    ticks = [15, 30, 60, 120, 240]
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.set_xlabel("average tokens/second (log scale)", fontsize=9, color=INK2)
    ax.set_ylabel("accuracy on 14 checkable questions", fontsize=9, color=INK2)
    ax.set_ylim(0, 1.05)
    ax.grid(color=GRID, linewidth=0.7, zorder=0)
    style_axes(ax)
    handles = [plt.Line2D([], [], marker="o", linestyle="none", color=c, markersize=8,
                          markeredgecolor=SURFACE, markeredgewidth=2, label=l)
               for l, c in [("SmolLM2-front bundle", "#2a78d6"), ("Qwen0.8B-front bundle", "#eb6834"), ("4B expert alone", "#52514e")]]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="lower left")
    ax.set_title("Accuracy vs speed - every mode sits on this tradeoff", fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(PLOTS / fname, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def scatter(recs, xkey, ykey, color_by_bundle, fname, xlabel, ylabel, title):
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    fig.patch.set_facecolor(SURFACE)
    seen = set()
    for r in recs:
        if r.get(xkey) is None or r.get(ykey) is None:
            continue
        color = BUNDLE_COLOR[r["bundle"]] if color_by_bundle else MODE_COLOR[mode_of(r["config"])]
        key = r["bundle"] if color_by_bundle else mode_of(r["config"])
        seen.add(key)
        ax.plot(r[xkey], r[ykey], "o", color=color, markersize=9,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
        ax.annotate(r["config"].split("/", 1)[1], (r[xkey], r[ykey]),
                    textcoords="offset points", xytext=(7, 5), fontsize=8, color=INK)
    ax.set_xlabel(xlabel, fontsize=9, color=INK2)
    ax.set_ylabel(ylabel, fontsize=9, color=INK2)
    ax.grid(color=GRID, linewidth=0.7, zorder=0)
    style_axes(ax)
    if color_by_bundle:
        handles = [plt.Line2D([], [], marker="o", linestyle="none", color=BUNDLE_COLOR[b], markersize=8,
                              markeredgecolor=SURFACE, markeredgewidth=2, label=BUNDLE_LABEL[b])
                   for b in ("muta-duo.gguf", "muta-duo-q.gguf") if b in seen]
    else:
        handles = [plt.Line2D([], [], marker="o", linestyle="none", color=MODE_COLOR[m], markersize=8,
                              markeredgecolor=SURFACE, markeredgewidth=2, label=m)
                   for m in MODE_ORDER if m in seen]
    ax.legend(handles=handles, frameon=False, fontsize=8)
    ax.set_title(title, fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(PLOTS / fname, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def score_chart(fname):
    rows = load(RUNS / "scores.jsonl")
    rows = [r for r in rows if r.get("S_total") is not None]
    if not rows:
        return
    bundles = ["muta-duo.gguf", "muta-duo-q.gguf"]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.2), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, bundle in zip(axes, bundles):
        sel = [r for r in rows if r["bundle"] == bundle]
        sel += [r for r in rows if r["config"].startswith("shared/")] if bundle == bundles[0] else []
        sel.sort(key=lambda r: r["S_total"])
        names = [r["config"].split("/", 1)[1] for r in sel]
        vals = [r["S_total"] for r in sel]
        colors = [MODE_COLOR[mode_of(r["config"])] for r in sel]
        hatches = ["///" if r.get("S_acc_imputed_from") else "" for r in sel]
        y = range(len(sel))
        bars = ax.barh(y, vals, height=0.62, color=colors, zorder=3)
        for b, h in zip(bars, hatches):
            b.set_hatch(h)
            if h:
                b.set_edgecolor(SURFACE)
        for i, v in enumerate(vals):
            ax.text(v, i, f" {v:.1f}", va="center", ha="left", fontsize=7.5, color=INK, zorder=5)
        ax.set_yticks(list(y), names, fontsize=8, color=INK)
        ax.set_title(BUNDLE_LABEL[bundle], fontsize=10, color=INK, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.7, zorder=0)
        style_axes(ax)
        ax.margins(x=0.12)
        ax.set_xlabel("S_total (official ADTC formula)", fontsize=9, color=INK2)
    fig.suptitle("ADTC leaderboard score: 0.50 S_acc + 0.30 S_perf + 0.20 S_eff  (hatched = S_acc imputed from measured sibling)",
                 fontsize=10.5, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(PLOTS / fname, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def main():
    PLOTS.mkdir(parents=True, exist_ok=True)
    perf = load(RUNS / "sweep.jsonl")
    acc = load(RUNS / "accuracy.jsonl")
    perf = [r for r in perf if "error" not in r]

    bar_panels(perf, "avg_tok_s", "tokens/second", "speed-by-config.png", max_key="max_tok_s")
    bar_panels(perf, "peak_rss_mib", "peak RSS (MiB)", "rss-by-config.png")
    if acc:
        pareto(acc, perf, "pareto-accuracy.png")
    ver = [r for r in perf if r.get("verify_acceptance") is not None]
    if ver:
        scatter(ver, "verify_acceptance", "avg_tok_s", True, "verify-acceptance.png",
                "mean draft acceptance rate", "average tokens/second",
                "Verify mode - acceptance drives speed, and the model pair drives acceptance")
    share = [r for r in perf if r.get("expert_share") is not None]
    if share:
        scatter(share, "expert_share", "avg_tok_s", False, "expert-share.png",
                "measured expert share of tokens (f)", "average tokens/second",
                "Expert share vs speed across co-authoring configs")
    score_chart("scores-by-config.png")
    print("plots written to", PLOTS)


if __name__ == "__main__":
    main()

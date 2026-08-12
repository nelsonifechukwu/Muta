#!/usr/bin/env python3
"""Official ADTC leaderboard scoring over the sweep results.

Implements the pinned profiler's published formula exactly (README, SHA 7adbe08f):

    S_total = 0.50*S_acc + 0.30*S_perf + 0.20*S_eff - P_thermal
    S_perf  = min(TPS / 15.0, 1.0) * 100          TPS_REFERENCE = 15.0
    S_eff   = max(0, (7.0 - peak_rss_gb) / 7.0) * 100   RAM_LIMIT_GB = 7.0
    P_thermal = 10 if throttled (not observed in these runs; see report)

TPS maps to generation throughput (the profiler reads llama-bench tg avg_ts; for
duo configs the analog is the session-average generation rate). S_acc is the
judge-ambiguous component: here it is measured on the 14-question checkable
"hidden prompt" suite (0-100); configs without a measured suite score inherit
their measured sibling's score, flagged imputed. Official arc_easy numbers from
the profiler runs are attached to raw models when present.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "bench/.runs"

TPS_REFERENCE = 15.0
RAM_LIMIT_GB = 7.0


def mode_class(config: str) -> str:
    name = config.split("/", 1)[1]
    if "alone" in name:
        return name
    return name.split("-")[0]


def load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]


def main():
    perf = [r for r in load(RUNS / "sweep.jsonl") if "error" not in r]
    acc = {r["config"]: r["accuracy"] for r in load(RUNS / "accuracy.jsonl")}

    # measured suite accuracy by (bundle, mode-class) for imputation
    by_class = {}
    for cfg, a in acc.items():
        r = next((p for p in perf if p["config"] == cfg), None)
        if r:
            by_class[(r["bundle"], mode_class(cfg))] = (a, cfg)
    # the shared expert row serves expert-alone for both bundles
    shared = next(((a, c) for (b, m), (a, c) in by_class.items() if m == "expert-alone"), None)

    rows = []
    for r in perf:
        tps = r.get("avg_tok_s") or 0.0
        rss_gb = (r.get("peak_rss_mib") or 0) / 1024.0
        s_perf = min(tps / TPS_REFERENCE, 1.0) * 100.0
        s_eff = max(0.0, (RAM_LIMIT_GB - rss_gb) / RAM_LIMIT_GB) * 100.0

        imputed_from = None
        if r["config"] in acc:
            s_acc = acc[r["config"]] * 100.0
        else:
            hit = by_class.get((r["bundle"], mode_class(r["config"])))
            if hit is None and mode_class(r["config"]) == "expert-alone" and shared:
                hit = shared
            if hit:
                s_acc, imputed_from = hit[0] * 100.0, hit[1]
            else:
                s_acc = None

        row = {
            "config": r["config"],
            "bundle": r["bundle"],
            "avg_tok_s": r.get("avg_tok_s"),
            "max_tok_s": r.get("max_tok_s"),
            "peak_rss_mib": r.get("peak_rss_mib"),
            "S_perf": round(s_perf, 1),
            "S_eff": round(s_eff, 1),
            "S_acc": round(s_acc, 1) if s_acc is not None else None,
            "S_acc_imputed_from": imputed_from,
            "P_thermal": 0,
        }
        if s_acc is not None:
            row["S_total"] = round(0.50 * s_acc + 0.30 * s_perf + 0.20 * s_eff, 1)
        rows.append(row)

    rows.sort(key=lambda x: -(x.get("S_total") or -1))
    out = RUNS / "scores.jsonl"
    with open(out, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    # markdown table
    md = ["| config | bundle | S_total | S_acc | S_perf | S_eff | avg tok/s | max tok/s | peak RSS |",
          "|---|---|---|---|---|---|---|---|---|"]
    for x in rows:
        dag = "†" if x["S_acc_imputed_from"] else ""
        md.append("| {c} | {b} | {t} | {a}{d} | {p} | {e} | {v} | {m} | {r} MiB |".format(
            c=x["config"], b=x["bundle"].replace("muta-duo", "").replace(".gguf", "") or "smol",
            t=x.get("S_total", "-"), a=x["S_acc"] if x["S_acc"] is not None else "-", d=dag,
            p=x["S_perf"], e=x["S_eff"], v=x["avg_tok_s"], m=x["max_tok_s"], r=x["peak_rss_mib"]))
    (RUNS / "scores_table.md").write_text("\n".join(md) + "\n")
    print(f"scored {len(rows)} configs -> {out}")


if __name__ == "__main__":
    main()

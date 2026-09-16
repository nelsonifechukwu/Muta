#!/usr/bin/env python3
"""Compute ADTC scores for the semi-final re-test from the audit JSONs + judge grades.

S_total = 0.50*S_acc + 0.30*S_perf + 0.20*S_eff - P_thermal
  S_perf    = min(TPS/15, 1)*100
  S_eff     = max(0, (7.0 - peak_rss_gb)/7.0)*100   (peak_rss_gb = peak_rss_mb/1000, the
                                                    profiler README's GB convention)
  P_thermal = 10 if throttled else 0
Cross-checked against bench/score.py (the repo's scoring module) on every row.

Usage: score_semis.py <artifact dir>
Reads  audit-<model>.json and judge-grades-<model>[-nothink].json, writes scores.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/oxowolabi/Developer/project/Muta")
from bench.score import score  # noqa: E402

ART = Path(sys.argv[1])
ROUND1 = {"acc": 39.20, "perf": 56.00, "eff": 90.65, "total": 54.53,
          "implied_tps": 0.56 * 15, "implied_peak_rss_mb": round((1 - 0.9065) * 7000, 1)}

# (model, condition label, grades file)
SETS = [
    ("qwen35-0.8b", "template_default (thinking on)", "judge-grades-qwen35-0.8b.json"),
    ("qwen35-0.8b", "thinking_off", "judge-grades-qwen35-0.8b-nothink.json"),
    ("qwen25-1.5b", "no thinking mode", "judge-grades-qwen25-1.5b.json"),
]


def s_eff(peak_mb: float) -> float:
    return max(0.0, (7.0 - peak_mb / 1000.0) / 7.0) * 100.0


def s_perf(tps: float) -> float:
    return min(tps / 15.0, 1.0) * 100.0


rows = []
for model, condition, grades_file in SETS:
    gpath = ART / grades_file
    if not gpath.exists():
        print(f"skip {model} / {condition}: {grades_file} missing")
        continue
    a = json.load(open(ART / f"audit-{model}.json"))
    g = json.load(open(gpath))
    tps = a["throughput"]["tokens_per_second_generation"]
    peak = a["memory"]["peak_rss_mb"]
    throttled = a["cpu_thermal"]["throttled"]
    temp = a["cpu_thermal"]["core_temp_c_peak"]
    arc = a["accuracy"][0]["score"] * 100.0
    scores = g["scores"]
    ids = sorted(scores)
    judge_pct = sum(scores[i] for i in ids) / len(ids) * 10.0
    auto = [scores[i] for i in ids if i.startswith("auto_")]
    human = [scores[i] for i in ids if i.startswith("judge_")]
    row = {
        "model": model,
        "judge_condition": condition,
        "tps": tps,
        "ttft_ms": a["throughput"]["first_token_latency_ms"],
        "peak_rss_mb": peak,
        "steady_rss_mb": a["memory"]["steady_state_rss_mb"],
        "throttled": throttled,
        "core_temp_c_peak": temp,
        "cpu_p99": a["cpu_thermal"]["cpu_percent_p99"],
        "params_count": a["model_info"]["params_count"],
        "params_match": a["model_info"]["params_match"],
        "arc_easy_50_pct": round(arc, 1),
        "judge_scores": {i: scores[i] for i in ids},
        "judge_prompt_pct": round(judge_pct, 1),
        "judge_auto_pct": round(sum(auto) / len(auto) * 10, 1),
        "judge_human_pct": round(sum(human) / len(human) * 10, 1),
        "S_perf": round(s_perf(tps), 2),
        "S_eff": round(s_eff(peak), 2),
        "P_thermal": 10.0 if throttled else 0.0,
    }
    for label, acc in (("arc", arc), ("judge", judge_pct)):
        r = score(accuracy=acc, tps_actual=tps, peak_rss_gb=peak / 1000.0,
                  max_temp_c=temp, throttled=throttled, label=f"{model}/{label}")
        manual = 0.5 * acc + 0.3 * s_perf(tps) + 0.2 * s_eff(peak) - (10 if throttled else 0)
        assert abs(r.s_total - manual) < 1e-6, (r.s_total, manual)
        row[f"S_acc_{label}"] = round(acc, 2)
        row[f"S_total_{label}"] = round(r.s_total, 2)
    rows.append(row)

json.dump({"round1_baseline": ROUND1, "formula": "0.50*S_acc + 0.30*min(TPS/15,1)*100 + 0.20*max(0,(7-peak_rss_gb)/7)*100 - 10*throttled",
           "rows": rows}, open(ART / "scores.json", "w"), indent=2)
print(f"{'model':12s} {'judge cond':32s} {'tok/s':>6s} {'peakMB':>8s} {'ARC50':>6s} {'judge%':>7s} {'S_perf':>7s} {'S_eff':>6s} {'T(arc)':>7s} {'T(judge)':>9s}")
for r in rows:
    print(f"{r['model']:12s} {r['judge_condition']:32s} {r['tps']:6.2f} {r['peak_rss_mb']:8.2f} {r['arc_easy_50_pct']:6.1f} {r['judge_prompt_pct']:7.1f} {r['S_perf']:7.2f} {r['S_eff']:6.2f} {r['S_total_arc']:7.2f} {r['S_total_judge']:9.2f}")
print(f"{'Round 1':12s} {'organisers (0.8B)':32s} {ROUND1['implied_tps']:6.2f} {ROUND1['implied_peak_rss_mb']:8.1f} {'':6s} {ROUND1['acc']:7.2f} {ROUND1['perf']:7.2f} {ROUND1['eff']:6.2f} {'':7s} {ROUND1['total']:9.2f}")

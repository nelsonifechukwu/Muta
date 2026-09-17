#!/usr/bin/env python3
"""Score audit JSONs with the ADTC formula, compute exchange-rate break-evens, shortlist
depths for healing, and (with --gate) issue the promotion verdict.

Usage:
  score_candidates.py --dir bench/measurements/prune-20260917 \
      --control bench/measurements/semifinal-20260916/audit-qwen25-1.5b.json \
      --out screen-scores.json
  score_candidates.py --dir … --control … --gate --out gate-scores.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bench.score import score

W_ACC, W_PERF, W_EFF = 0.50, 0.30, 0.20
PROMOTE_MARGIN = 1.0
GSM8K_MAX_DROP = 0.05


def _components(tps: float, peak_mb: float) -> tuple[float, float]:
    return min(tps / 15.0, 1.0) * 100.0, max(0.0, (7.0 - peak_mb / 1000.0) / 7.0) * 100.0


def row_from_audit(name: str, audit: dict) -> dict:
    tps = audit["throughput"]["tokens_per_second_generation"]
    peak = audit["memory"]["peak_rss_mb"]
    throttled = bool(audit["cpu_thermal"]["throttled"])
    temp = audit["cpu_thermal"].get("core_temp_c_peak")
    arc50 = audit["accuracy"][0]["score"] * 100.0 if audit["accuracy"] else None
    s_perf, s_eff = _components(tps, peak)
    row = {
        "name": name,
        "layers": int(m.group(1)) if (m := re.search(r"-(\d+)L", name)) else 28,
        "tps": tps,
        "peak_rss_mb": peak,
        "throttled": throttled,
        "params_match": audit.get("model_info", {}).get("params_match"),
        "arc_easy_50": arc50,
        "S_perf": round(s_perf, 2),
        "S_eff": round(s_eff, 2),
    }
    if arc50 is not None:
        r = score(accuracy=arc50, tps_actual=tps, peak_rss_gb=peak / 1000.0,
                  max_temp_c=temp, throttled=throttled, label=name)
        row["S_total_arc50"] = round(r.s_total, 2)
    return row


def break_even_accuracy_loss(control: dict, candidate: dict) -> float:
    """Accuracy points the candidate may lose and still tie the control on S_total."""
    gain = (W_PERF * (candidate["S_perf"] - control["S_perf"])
            + W_EFF * (candidate["S_eff"] - control["S_eff"]))
    return gain / W_ACC


def shortlist(rows: list[dict], control: dict, max_depths: int = 2) -> list[dict]:
    """Top depths by unhealed S_total whose ARC-50 floor is within 2× break-even of control."""
    eligible = []
    for row in rows:
        be = break_even_accuracy_loss(control, row)
        loss = control["arc_easy_50"] - row["arc_easy_50"]
        row = dict(row, break_even=round(be, 2), arc50_loss=round(loss, 2))
        if loss <= 2.0 * be:
            eligible.append(row)
    eligible.sort(key=lambda r: -r["S_total_arc50"])
    picked, depths = [], set()
    for row in eligible:
        if row["layers"] in depths:
            continue
        picked.append(row)
        depths.add(row["layers"])
        if len(picked) == max_depths:
            break
    return picked


def verdict(candidate: dict, published: dict) -> dict:
    checks = {
        "arc500_total": candidate["S_total_arc500"] >= published["S_total_arc500"] + PROMOTE_MARGIN,
        "judge_total": candidate["S_total_judge"] >= published["S_total_judge"] + PROMOTE_MARGIN,
        "gsm8k": candidate["gsm8k_40"] >= published["gsm8k_40"] - GSM8K_MAX_DROP,
        "params_match": bool(candidate.get("params_match")),
    }
    return {"promote": all(checks.values()), "checks": checks}


def _gate_row(row: dict, directory: Path) -> dict:
    battery = directory / f"battery-{row['name']}.json"
    grades = directory / f"judge-grades-{row['name']}.json"
    if battery.exists():
        b = json.loads(battery.read_text())
        row["arc_easy_500"] = b["arc_easy"]["score"] * 100.0
        row["arc_challenge_100"] = b["arc_challenge"]["score"]
        row["gsm8k_40"] = b["gsm8k"]["score"]
        r = score(accuracy=row["arc_easy_500"], tps_actual=row["tps"],
                  peak_rss_gb=row["peak_rss_mb"] / 1000.0,
                  throttled=row["throttled"], label=row["name"])
        row["S_total_arc500"] = round(r.s_total, 2)
    if grades.exists():
        g = json.loads(grades.read_text())["scores"]
        row["judge_pct"] = sum(g.values()) / len(g) * 10.0
        r = score(accuracy=row["judge_pct"], tps_actual=row["tps"],
                  peak_rss_gb=row["peak_rss_mb"] / 1000.0,
                  throttled=row["throttled"], label=row["name"])
        row["S_total_judge"] = round(r.s_total, 2)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True,
                         help="audit JSON of the published 28L file")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    control = row_from_audit("published-28L", json.loads(args.control.read_text()))
    rows = [row_from_audit(p.stem.removeprefix("audit-"), json.loads(p.read_text()))
            for p in sorted(args.dir.glob("audit-*.json"))]
    rows = [r for r in rows if r["name"] != control["name"]]
    result: dict = {"control": control, "rows": rows}
    if args.gate:
        control = _gate_row(control, args.dir)
        rows = [_gate_row(r, args.dir) for r in rows]
        result["verdicts"] = {
            r["name"]: verdict(r, control)
            for r in rows if "S_total_judge" in r and "S_total_arc500" in r
        }
    else:
        result["shortlist"] = shortlist(rows, control)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{'name':36s} {'L':>3s} {'tok/s':>6s} {'peakMB':>8s} {'ARC50':>6s} "
          f"{'S_perf':>7s} {'S_eff':>6s} {'T(arc50)':>9s}")
    for r in [control] + rows:
        print(f"{r['name']:36s} {r['layers']:3d} {r['tps']:6.2f} {r['peak_rss_mb']:8.1f} "
              f"{r.get('arc_easy_50') or 0:6.1f} {r['S_perf']:7.2f} {r['S_eff']:6.2f} "
              f"{r.get('S_total_arc50') or 0:9.2f}")
    if not args.gate:
        print("shortlist:", [r["name"] for r in result["shortlist"]])
    else:
        print(json.dumps(result["verdicts"], indent=2))


if __name__ == "__main__":
    main()

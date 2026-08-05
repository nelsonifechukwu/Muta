"""Composite S_total table for the 2026-08-05 campaign — reads bakeoff.jsonl.

Scenario S (audit docker, SSE-only b10175): TPS anchored on an unknown absolute for the
stock 4B (parameter --audit-tps-4b, default 2.0 tok/s); per-candidate factors from the
kernel map (Q4_0 SSSE3 ≈ 1.65x stock; K-quant variants ~ scalar-byte ratio; 2B ~ 1/params
compute-bound ≈ 2.3x). RSS = measured x86sse probe (file + ~0) + 0.05 GB profiler python.

Scenario L (Standard Laptop AVX2, repack-off measurement build): TPS = BW / file_GiB
(default BW 28 GiB/s effective), RSS = file + 0.4 GB.

S_acc proxy = mean(arc_easy, arc_challenge, sciq, gsm8k-strict) x 100. 4B quant variants
borrow stock's arc_challenge/sciq (same-model approximation; MCQ deltas are inside noise).

Usage: python3 bench/score_campaign.py [--audit-tps-4b 2.0] [--bw 28] [--tps-max 15]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The committed evidence. Point --rows at bench/.artifacts/bakeoff.jsonl to score a live
# (still-running) campaign instead.
ROWS = ROOT / "bench" / "measurements" / "bakeoff-20260805.jsonl"

GIB = 2**30

# file bytes, audit-TPS factor vs stock 4B Q4_K_M (kernel-map reasoning), notes
CANDS = {
    "Qwen3.5-4B-Q4_K_M.gguf": (2740937888, 1.00, "stock"),
    "Qwen3.5-4B-Q4_0.gguf": (2583221408, 1.65, "SSSE3 body; Q6_K head scalar"),
    "Qwen3.5-4B-UD-Q4_K_XL.gguf": (2912109728, 0.95, "scalar K-quants, bigger"),
    "Qwen3.5-4B-UD-Q3_K_XL.gguf": (2436420768, 1.05, "scalar; fewer bytes; 48xF16 slow"),
    "Qwen3.5-4B-IQ4_XS.gguf": (2477053088, 0.70, "IQ scalar dequant is worst"),
    "Qwen3.5-2B-Q4_K_M.gguf": (1280835840, 2.30, "~1/2 params compute-bound"),
    "Qwen3.5-2B-Q6_K.gguf": (1574961408, 2.10, "2B, K-quant scalar body"),
    "Qwen3.5-4B-Q4_0-EH.gguf": (2380008352, 2.00, "ALL tensors SSSE3-vectorized incl head"),
    "Qwen3.5-0.8B-Q4_K_M.gguf": (532517120, 5.00, "floor reference"),
}

TASKS = ("arc_easy", "arc_challenge", "sciq", "gsm8k")


def load_acc(rows: Path = ROWS) -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, float]] = {}
    for line in rows.read_text().splitlines():
        r = json.loads(line)
        if r.get("kind") != "accuracy" or not r.get("ok"):
            continue
        if r.get("metric") == "sample_len":  # the upstream extraction bug rows
            continue
        acc.setdefault(r["model"], {})[r["benchmark"]] = float(r["score"])
    return acc


def s_acc_proxy(model: str, acc: dict[str, dict[str, float]]) -> tuple[float | None, str]:
    stock = acc.get("Qwen3.5-4B-Q4_K_M.gguf", {})
    mine = acc.get(model, {})
    vals, borrowed = [], []
    for t in TASKS:
        if t in mine:
            vals.append(mine[t])
        elif model.startswith("Qwen3.5-4B") and t in stock:
            vals.append(stock[t])
            borrowed.append(t)
        else:
            return None, f"missing {t}"
    note = f"borrowed:{','.join(borrowed)}" if borrowed else ""
    return 100.0 * sum(vals) / len(vals), note


def s_perf(tps: float, tps_max: float) -> float:
    return 100.0 * min(tps / tps_max, 1.0)


def s_eff(rss_gb: float) -> float:
    return max(0.0, (7.0 - rss_gb) / 7.0) * 100.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=Path, default=ROWS, help="bake-off JSONL to score")
    ap.add_argument("--audit-tps-4b", type=float, default=2.0,
                    help="assumed audit-build tg for stock 4B Q4_K_M (unknown; sensitivity axis)")
    ap.add_argument("--bw", type=float, default=28.0, help="laptop effective GiB/s")
    ap.add_argument("--tps-max", type=float, default=15.0)
    args = ap.parse_args()

    acc = load_acc(args.rows)
    print(f"scenario S: audit-4B-tg={args.audit_tps_4b}; scenario L: BW={args.bw} GiB/s; "
          f"tps_max={args.tps_max}; S_acc = 4-task mean x100\n")
    hdr = (f"{'candidate':34s} {'GiB':>5s} {'Sacc':>5s} | {'tgS':>5s} {'SperfS':>6s} "
           f"{'SeffS':>5s} {'S(S)':>6s} | {'tgL':>5s} {'SperfL':>6s} {'SeffL':>5s} {'S(L)':>6s}")
    print(hdr)
    rows = []
    for model, (nbytes, factor, _note) in CANDS.items():
        sacc, note = s_acc_proxy(model, acc)
        if sacc is None:
            print(f"{model:34s} {nbytes / GIB:5.2f}  (accuracy incomplete: {note})")
            continue
        gib = nbytes / GIB
        # Scenario S
        tg_s = args.audit_tps_4b * factor
        rss_s = gib + 0.45  # file + ctx/compute + profiler python (x86sse probe ≈ file)
        total_s = 0.5 * sacc + 0.3 * s_perf(tg_s, args.tps_max) + 0.2 * s_eff(rss_s)
        # Scenario L (repack-off measurement build)
        tg_l = args.bw / gib
        rss_l = gib + 0.40
        total_l = 0.5 * sacc + 0.3 * s_perf(tg_l, args.tps_max) + 0.2 * s_eff(rss_l)
        rows.append((total_s, total_l, model, gib, sacc, tg_s, rss_s, tg_l, rss_l, note))

    for total_s, total_l, model, gib, sacc, tg_s, rss_s, tg_l, rss_l, note in sorted(
        rows, key=lambda r: -(r[0] + r[1])
    ):
        print(f"{model:34s} {gib:5.2f} {sacc:5.1f} | {tg_s:5.2f} {s_perf(tg_s, args.tps_max):6.1f} "
              f"{s_eff(rss_s):5.1f} {total_s:6.2f} | {tg_l:5.2f} {s_perf(tg_l, args.tps_max):6.1f} "
              f"{s_eff(rss_l):5.1f} {total_l:6.2f}  {note}")


if __name__ == "__main__":
    main()

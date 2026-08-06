"""Per-platform S_total / S_acc / S_perf / S_eff table from RECORDED measurements only.

Every throughput and RSS number below carries a provenance tag and is transcribed from a
dated measurement; nothing is invented at print time. Cells we never measured are shown as
`--` in the measured table and only filled (marked `~`) in the projected table, where the
model used is stated in the header.

    S_acc  = mean(arc_easy, arc_challenge, sciq, gsm8k-strict) x 100   [measured]
    S_perf = 100 * min(tok/s / tps_max, 1)                             [tps_max default 15]
    S_eff  = 100 * max(0, (7 - peak_rss_gb) / 7)
    S_tot  = 0.50*S_acc + 0.30*S_perf + 0.20*S_eff        (P_thermal = 0: never measured)

Usage:  python3 bench/score_table.py [--tps-max 15] [--bw 28]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROWS = ROOT / "bench" / "measurements" / "bakeoff-20260805.jsonl"
GIB = 2**30

# --- the candidate roster: file bytes on disk -------------------------------------------
FILES = {
    "4B Q4_K_M (stock)": 2740937888,
    "4B Q4_0": 2583221408,
    "4B Q4_0-EH (ours)": 2380008352,
    "4B UD-Q4_K_XL": 2912109728,
    "4B UD-Q3_K_XL": 2436420768,
    "4B IQ4_XS": 2477053088,
    "2B Q4_K_M": 1280835840,
    "2B Q6_K": 1574961408,
    "0.8B Q4_K_M": 532517120,
}
# bakeoff.jsonl model-file names -> display names above
JSONL_NAME = {
    "Qwen3.5-4B-Q4_K_M.gguf": "4B Q4_K_M (stock)",
    "Qwen3.5-4B-Q4_0.gguf": "4B Q4_0",
    "Qwen3.5-4B-Q4_0-EH.gguf": "4B Q4_0-EH (ours)",
    "Qwen3.5-4B-UD-Q4_K_XL.gguf": "4B UD-Q4_K_XL",
    "Qwen3.5-4B-UD-Q3_K_XL.gguf": "4B UD-Q3_K_XL",
    "Qwen3.5-4B-IQ4_XS.gguf": "4B IQ4_XS",
    "Qwen3.5-2B-Q4_K_M.gguf": "2B Q4_K_M",
    "Qwen3.5-2B-Q6_K.gguf": "2B Q6_K",
    "Qwen3.5-0.8B-Q4_K_M.gguf": "0.8B Q4_K_M",
}

# --- RECORDED throughput (decode tok/s) -------------------------------------------------
# Each entry: (value, provenance). Multiple rounds -> the max, per this repo's convention
# of reporting warm maxima, with the round values kept in the provenance string.
TG = {
    # x86 SSE-only b10175 = the audit image's kernel map, run under Rosetta 2 on the M2.
    # RATIO SIGNAL ONLY: Rosetta translation makes absolutes meaningless, and the probes
    # were -p 32 -n 16 -r 1 under load 9-74 (RESULTS 2026-08-05 §D2).
    ("audit-sse-rosetta", "4B Q4_K_M (stock)"): (5.45, "2026-08-05 probe#2 rounds 2.96/5.45"),
    ("audit-sse-rosetta", "4B Q4_0"): (6.54, "2026-08-05 probe#2 rounds 5.87/6.54"),
    ("audit-sse-rosetta", "4B Q4_0-EH (ours)"): (6.76, "2026-08-05 probe#2 rounds 6.61/6.76"),
    # Dev-host native arm64 llama-bench, -ngl 0 (RESULTS 2026-08-04 §B, 2 interleaved rounds)
    ("dev-native-arm64", "4B Q4_K_M (stock)"): (26.46, "2026-08-04 26.46+-0.83 / 25.94+-1.42"),
    ("dev-native-arm64", "0.8B Q4_K_M"): (103.96, "2026-08-04 96.15+-9.33 / 103.96+-4.29"),
    # Dev-host docker, linux/amd64 AVX2 engine under emulation (RESULTS 2026-08-04 §B)
    ("dev-docker-x86", "4B Q4_K_M (stock)"): (3.89, "2026-08-04 3.89+-0.09"),
    ("dev-docker-x86", "0.8B Q4_K_M"): (7.59, "2026-08-04 7.59+-0.12"),
}

# --- RECORDED peak RSS (GB, whole llama-bench tree) -------------------------------------
RSS = {
    # `time -l` maximum resident, mini-bench, Rosetta. macOS reclaims file-backed pages
    # under pressure, so the AVX2/AVX rows are pressure-confounded (RESULTS 2026-08-05 §D).
    ("audit-sse-rosetta", "4B Q4_K_M (stock)"): (2.83, "2026-08-05 time -l, x86sse"),
    ("audit-sse-rosetta", "4B Q4_0"): (2.44, "2026-08-05 time -l, x86sse"),
    ("dev-native-arm64", "4B Q4_K_M (stock)"): (5.28, "2026-08-04 sampled tree RSS 5.08/5.28"),
    ("dev-native-arm64", "0.8B Q4_K_M"): (1.26, "2026-08-04 sampled tree RSS"),
    ("dev-docker-x86", "4B Q4_K_M (stock)"): (4.36, "2026-08-04 mmap+AVX2 repack+ctx"),
    ("dev-docker-x86", "0.8B Q4_K_M"): (0.88, "2026-08-04"),
}

PLATFORMS = {
    "audit-sse-rosetta": "ADTC audit image kernel map (b10175, all SIMD off) — via Rosetta",
    "dev-native-arm64": "Dev host, native arm64 (M2 Pro)",
    "dev-docker-x86": "Dev host, docker linux/amd64 AVX2 (emulated)",
}


def load_acc() -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, float]] = {}
    for line in ROWS.read_text().splitlines():
        r = json.loads(line)
        if r.get("kind") != "accuracy" or not r.get("ok") or r.get("metric") == "sample_len":
            continue
        name = JSONL_NAME.get(r["model"])
        if name:
            acc.setdefault(name, {})[r["benchmark"]] = float(r["score"])
    return acc


TASKS = ("arc_easy", "arc_challenge", "sciq", "gsm8k")


def s_acc(model: str, acc: dict[str, dict[str, float]]) -> tuple[float | None, bool]:
    """(score, fully_measured). 4B variants borrow the stock 4B's untested MCQ tasks."""
    mine, stock = acc.get(model, {}), acc.get("4B Q4_K_M (stock)", {})
    vals, borrowed = [], False
    for t in TASKS:
        if t in mine:
            vals.append(mine[t])
        elif model.startswith("4B") and t in stock:
            vals.append(stock[t])
            borrowed = True
        else:
            return None, False
    return 100.0 * sum(vals) / len(vals), not borrowed


def s_perf(tps: float, tps_max: float) -> float:
    return 100.0 * min(tps / tps_max, 1.0)


def s_eff(rss: float) -> float:
    return max(0.0, (7.0 - rss) / 7.0) * 100.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tps-max", type=float, default=15.0)
    ap.add_argument("--bw", type=float, default=28.0, help="GiB/s for the projected laptop")
    args = ap.parse_args()
    acc = load_acc()

    print("=" * 100)
    print("TABLE 1 — MEASURED ONLY.  '--' = never measured on that platform (not modelled).")
    print(f"S_perf at tps_max={args.tps_max}.  P_thermal never measured on any platform.")
    print("=" * 100)
    for plat, label in PLATFORMS.items():
        print(f"\n### {label}")
        print(f"{'model':22s} {'GiB':>5s} {'S_acc':>6s} {'tok/s':>7s} {'S_perf':>7s} "
              f"{'RSS GB':>7s} {'S_eff':>6s} {'S_total':>8s}")
        for model, nbytes in FILES.items():
            a, full = s_acc(model, acc)
            tg = TG.get((plat, model))
            rss = RSS.get((plat, model))
            if a is None and tg is None and rss is None:
                continue
            acc_s = "--" if a is None else f"{a:.1f}{'' if full else '~'}"
            tg_s = "--" if tg is None else f"{tg[0]:.2f}"
            perf_s = "--" if tg is None else f"{s_perf(tg[0], args.tps_max):.1f}"
            rss_s = "--" if rss is None else f"{rss[0]:.2f}"
            eff_s = "--" if rss is None else f"{s_eff(rss[0]):.1f}"
            if a is not None and tg is not None and rss is not None:
                tot = 0.5 * a + 0.3 * s_perf(tg[0], args.tps_max) + 0.2 * s_eff(rss[0])
                tot_s = f"{tot:.2f}"
            else:
                tot_s = "--"
            print(f"{model:22s} {nbytes / GIB:5.2f} {acc_s:>6s} {tg_s:>7s} {perf_s:>7s} "
                  f"{rss_s:>7s} {eff_s:>6s} {tot_s:>8s}")

    print("\n" + "=" * 100)
    print("TABLE 2 — PROJECTED to the two platforms that decide the score. All S_perf/S_eff")
    print("cells here are MODELLED (~); only S_acc is measured.")
    print("  Standard Laptop (AVX2, repack-off build): tok/s = BW / file_GiB "
          f"(BW={args.bw} GiB/s); RSS = file + 0.40 GB")
    print("  Audit image (SSE-only, no repack): tok/s = anchor x measured/derived kernel")
    print("  factor; RSS = file + 0.45 GB.  Anchor for the 4B stock is UNKNOWN — see note.")
    print("=" * 100)
    # kernel-map factors relative to the 4B stock: measured for the three probed files,
    # reasoned for the rest (IQ = slowest scalar dequant, 2B ~ half the params).
    FACTORS = {
        "4B Q4_K_M (stock)": (1.00, "anchor"),
        "4B Q4_0": (1.20, "measured 6.54/5.45"),
        "4B Q4_0-EH (ours)": (1.24, "measured 6.76/5.45"),
        "4B UD-Q4_K_XL": (0.95, "reasoned: scalar, bigger"),
        "4B UD-Q3_K_XL": (1.05, "reasoned: scalar, smaller"),
        "4B IQ4_XS": (0.70, "reasoned: IQ scalar dequant"),
        "2B Q4_K_M": (2.30, "reasoned: ~1/2 params"),
        "2B Q6_K": (2.10, "reasoned"),
        "0.8B Q4_K_M": (5.00, "reasoned"),
    }
    for anchor in (2.0, 5.0):
        print(f"\n### Audit image, assuming stock-4B = {anchor} tok/s")
        print(f"{'model':22s} {'GiB':>5s} {'S_acc':>6s} {'~tok/s':>7s} {'S_perf':>7s} "
              f"{'~RSS':>6s} {'S_eff':>6s} {'S_total':>8s}  factor")
        rows = []
        for model, nbytes in FILES.items():
            a, full = s_acc(model, acc)
            if a is None:
                continue
            gib = nbytes / GIB
            f, why = FACTORS[model]
            tg, rss = anchor * f, gib + 0.45
            tot = 0.5 * a + 0.3 * s_perf(tg, args.tps_max) + 0.2 * s_eff(rss)
            rows.append((tot, model, gib, a, full, tg, rss, why))
        for tot, model, gib, a, full, tg, rss, why in sorted(rows, reverse=True):
            print(f"{model:22s} {gib:5.2f} {a:5.1f}{'' if full else '~'} {tg:7.2f} "
                  f"{s_perf(tg, args.tps_max):7.1f} {rss:6.2f} {s_eff(rss):6.1f} {tot:8.2f}  {why}")

    print(f"\n### Standard Laptop (AVX2, repack-off), BW={args.bw} GiB/s")
    print(f"{'model':22s} {'GiB':>5s} {'S_acc':>6s} {'~tok/s':>7s} {'S_perf':>7s} "
          f"{'~RSS':>6s} {'S_eff':>6s} {'S_total':>8s}")
    rows = []
    for model, nbytes in FILES.items():
        a, full = s_acc(model, acc)
        if a is None:
            continue
        gib = nbytes / GIB
        tg, rss = args.bw / gib, gib + 0.40
        tot = 0.5 * a + 0.3 * s_perf(tg, args.tps_max) + 0.2 * s_eff(rss)
        rows.append((tot, model, gib, a, full, tg, rss))
    for tot, model, gib, a, full, tg, rss in sorted(rows, reverse=True):
        print(f"{model:22s} {gib:5.2f} {a:5.1f}{'' if full else '~'} {tg:7.2f} "
              f"{s_perf(tg, args.tps_max):7.1f} {rss:6.2f} {s_eff(rss):6.1f} {tot:8.2f}")
    print("\n~ on S_acc = 2 of 4 tasks measured, the other two borrowed from the stock 4B.")


if __name__ == "__main__":
    main()

"""Decode-throughput ceiling from memory bandwidth (cactus-inspired diagnostic).

CPU decode of a dense GGUF is memory-bandwidth-bound: each generated token streams
essentially the whole weight file once. Cactus publishes "% of theoretical ceiling"
per device (iPhone 17 Pro: 140 measured of ~169 theoretical tok/s = 83%, from
~60 GB/s over a 355 MB model) and uses it to decide when thread tuning is DONE.

    python -m bench.ceiling --model models/core/Qwen3.5-4B-Q4_K_M.gguf --measured 31.1

bytes/token = the model file size. Assumptions stated so the number is honest:
- the AVX2/arm repacked copy is the same bytes, read once per token;
- attention-KV reads at -c 2048 on this hybrid (~24.5 KiB/token) are <2% and ignored;
- the 50 MiB SSM state is re-read per token but is likewise ~2% of 2.5 GiB.
So the ceiling is OPTIMISTIC by a few percent — good enough for "keep tuning or stop",
and for predicting the x86 target box's decode from its bandwidth before we have it.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def ceiling_tps(bandwidth_bytes_s: float, bytes_per_token: float) -> float:
    if bytes_per_token <= 0:
        return float("inf")
    return bandwidth_bytes_s / bytes_per_token


def measure_copy_bandwidth_bytes_s(size_mib: int = 512, passes: int = 5) -> float:
    """Best-of-N large-copy bandwidth (reads + writes counted, STREAM-copy style).

    numpy memcpy underestimates true peak DRAM bandwidth somewhat; that bias makes
    the resulting ceiling conservative, which is the safe direction for a stop rule.
    """
    import numpy as np

    a = np.ones(size_mib * 2**20 // 8, dtype=np.float64)
    b = np.empty_like(a)
    best = 0.0
    for _ in range(passes):
        t0 = time.perf_counter()
        np.copyto(b, a)
        dt = time.perf_counter() - t0
        best = max(best, 2 * a.nbytes / dt)
    return best


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ceiling", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", type=Path, required=True, help="GGUF whose size = bytes/token")
    p.add_argument("--measured", type=float, default=None, help="measured decode tok/s to grade")
    p.add_argument("--bandwidth-gib-s", type=float, default=None,
                   help="skip the probe and use this bandwidth (e.g. the x86 target's spec sheet)")
    args = p.parse_args(argv)

    bytes_per_token = args.model.stat().st_size
    bw = (args.bandwidth_gib_s * 2**30) if args.bandwidth_gib_s else measure_copy_bandwidth_bytes_s()
    ceil = ceiling_tps(bw, bytes_per_token)

    print(f"model            {args.model}  ({bytes_per_token / 2**30:.2f} GiB)")
    print(f"bandwidth        {bw / 2**30:.1f} GiB/s" + ("  (asserted)" if args.bandwidth_gib_s else "  (measured copy)"))
    print(f"ceiling          {ceil:.1f} tok/s")
    if args.measured is not None:
        print(f"measured         {args.measured:.1f} tok/s  ({100 * args.measured / ceil:.0f}% of ceiling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

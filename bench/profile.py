"""The product-path pass — measure what the official profiler never touches.

The profiler scores `llama-bench` against the GGUF. Our gateway, FastAPI, SQLite and (later)
FAISS and the embedder are never in the tree it walks. That gap is not scored, but it is where
a **disqualification** lives: an OOM kill is a hard failure, not a deduction (CLAUDE.md). So
this pass exercises the real path — POST /v1/chat, through the contract, like every other
client — and samples the whole tree while it runs.

Prompts come from the checked-in submission metadata, so the product path is exercised with
exactly the prompts the competition sees.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import psutil

from bench.adtc.report import MeasuredRun, from_samplers
from bench.adtc.submission import test_prompts
from bench.sampler import ThermalSampler, TreeSampler

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_ENGINE_PORT = 8080
REQUEST_TIMEOUT_S = 300.0


@dataclass(frozen=True)
class ProductRun:
    run: MeasuredRun
    replies: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _collect_metrics(base_url: str) -> dict | None:
    try:
        r = httpx.get(f"{base_url}/internal/bench/metrics", timeout=2.0)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _resolve_pids(base_url: str, engine_port: int) -> list[int]:
    """Gateway + engine. They are siblings, so one PID is never the whole footprint."""
    from bench.monitor import resolve_engine_pid, resolve_pid

    port = int(base_url.rsplit(":", 1)[-1].split("/")[0])
    pids = [resolve_pid(None, port=port)]
    engine_pid = resolve_engine_pid(engine_port)
    if engine_pid:
        pids.append(engine_pid)
    return pids


def run_product_path(
    *,
    base_url: str = DEFAULT_BASE_URL,
    pid: int | None = None,
    engine_port: int = DEFAULT_ENGINE_PORT,
    prompts: list[dict] | None = None,
    warmup: bool = True,
) -> ProductRun:
    """Replay the submission prompts through /v1/chat, sampling gateway + engine."""
    prompts = prompts if prompts is not None else test_prompts()
    pids = [pid] if pid is not None else _resolve_pids(base_url, engine_port)
    target_pid = pids[0]

    memory = TreeSampler()
    thermal = ThermalSampler()
    memory.start(pids)
    thermal.start()

    replies: list[str] = []
    errors: list[str] = []
    response_rates: list[float] = []

    try:
        if warmup:
            # The first generation pays model load and a cold prompt cache. Including it would
            # understate steady-state TPS and measure provisioning, not decoding.
            try:
                httpx.post(
                    f"{base_url}/v1/chat",
                    json={"student_id": "bench-warmup", "message": "Say OK."},
                    timeout=REQUEST_TIMEOUT_S,
                )
            except httpx.HTTPError:
                pass

        for item in prompts:
            try:
                r = httpx.post(
                    f"{base_url}/v1/chat",
                    json={"student_id": "bench", "message": item["prompt"]},
                    timeout=REQUEST_TIMEOUT_S,
                )
                r.raise_for_status()
                body = r.json()
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{item.get('prompt_id', '?')}: {type(e).__name__}: {e}")
                continue
            replies.append(body.get("reply", ""))
            timings = body.get("_timings") or {}
            rate = timings.get("tokens_per_second")
            if isinstance(rate, (int, float)) and rate > 0:
                response_rates.append(float(rate))
    finally:
        memory.stop()
        thermal.stop()

    # Prefer the app's own rolling window; it reads the engine's timings directly.
    metrics = _collect_metrics(base_url)
    if metrics and metrics.get("avg_tps"):
        tps, from_wall_clock = float(metrics["avg_tps"]), False
    elif response_rates:
        tps, from_wall_clock = sum(response_rates) / len(response_rates), True
    else:
        tps, from_wall_clock = 0.0, True

    crashed = bool(errors) or not psutil.pid_exists(target_pid)

    run = from_samplers(
        memory.report(),
        thermal.report(),
        tps_actual=tps,
        source="product",
        tps_from_wall_clock=from_wall_clock,
        oom_or_crash=crashed,
    )
    return ProductRun(run=run, replies=replies, errors=errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="muta-profile", description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--engine-port", type=int, default=DEFAULT_ENGINE_PORT)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_product_path(
            base_url=args.base_url,
            pid=args.pid,
            engine_port=args.engine_port,
            warmup=not args.no_warmup,
        )
    except Exception as e:  # noqa: BLE001 — every attach failure is already self-describing
        print(f"error: {e}", file=sys.stderr)
        return 1

    run = result.run
    temp = f"{run.max_temp_c:.1f} °C" if run.max_temp_c is not None else "—"
    print(
        f"product path: {run.tps_actual:.2f} tok/s  "
        f"peak {run.peak_rss_gb:.2f} GB  steady {run.steady_rss_gb:.2f} GB  temp {temp}"
    )
    for err in result.errors:
        print(f"  error: {err}", file=sys.stderr)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(run.__dict__, indent=2, default=str) + "\n")

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

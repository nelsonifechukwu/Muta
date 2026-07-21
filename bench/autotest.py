"""Autonomous measurement: both paths, both scored, one command.

    make profile

Two paths are run because they fail differently:

- **The scored path** — the official profiler against the GGUF. This is the number the audit
  reproduces, and a self-reported figure that misses by 2x is a *fail*, not a lower score.
- **The product path** — our two-process stack under real prompts. Never scored by the
  profiler, but where an OOM kill lives, and an OOM kill is a disqualification.

A harness that ran only the scored path would report a healthy number for a submission that
cannot survive its own audit.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bench.adtc import install, submission
from bench.adtc.report import from_profiler_json, params_match, score_run
from bench.score import ScoreResult

_BENCH = Path(__file__).resolve().parent
ARTIFACT_DIR = _BENCH / ".artifacts"
RUNS_JSONL = ARTIFACT_DIR / "runs.jsonl"
OPTIMIZATION_LOG = _BENCH / "optimization-log.md"

# Accuracy is not measured here. The hidden 30% subset is unpublished and lm-eval runs against
# the raw GGUF, so our tutoring layer is invisible to it (docs/rules-digest.md Q6). Held
# constant so S_perf and S_eff movement is attributable; recorded in every artifact.
ASSUMED_ACCURACY = 50.0


class AutotestError(RuntimeError):
    """The autonomous run could not complete."""


@dataclass(frozen=True)
class Provenance:
    system: str
    machine: str
    git_sha: str
    label: str


def capture_provenance() -> Provenance:
    """Stamp the host. Report-grade numbers come only from the x86 target box (CLAUDE.md)."""
    system = platform.system()
    machine = platform.machine()
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
        if dirty:
            sha += "-dirty"
    except (subprocess.SubprocessError, OSError):
        sha = "unknown"

    provisional = system == "Darwin" or machine in {"arm64", "aarch64"}
    return Provenance(
        system=system,
        machine=machine,
        git_sha=sha,
        label="dev_host_provisional" if provisional else "target_candidate",
    )


def find_llama_bench_dir() -> Path | None:
    """Where our llama-bench lives. The profiler resolves it via shutil.which only."""
    build_bin = _BENCH.parent / "runtime" / "build" / "bin"
    if (build_bin / "llama-bench").is_file():
        return build_bin
    from shutil import which

    found = which("llama-bench")
    return Path(found).parent if found else None


def run_official(binary: Path, submission_dir: Path, output: Path, *, extra_path: Path | None) -> dict:
    """Invoke the real profiler and return its parsed report."""
    env = dict(os.environ)
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"

    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(binary),
            "run",
            "--submission",
            str(submission_dir),
            "--mode",
            "participant",
            "--output",
            str(output),
            "--skip-accuracy",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=3600,
    )
    if proc.returncode != 0:
        raise AutotestError(
            f"adtc-profiler exited {proc.returncode}\n"
            f"  stdout:\n{proc.stdout[-2000:]}\n"
            f"  stderr:\n{proc.stderr[-2000:]}"
        )
    if not output.is_file():
        raise AutotestError(f"profiler reported success but wrote nothing to {output}")
    return json.loads(output.read_text())


def log_row(scored: dict, provenance: Provenance) -> str:
    """One markdown row for bench/optimization-log.md."""
    prof = scored.get("profiler") or {}
    prod = scored.get("product") or {}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def total(block: dict) -> str:
        value = block.get("s_total")
        return f"{value:.1f}" if isinstance(value, (int, float)) else "DQ"

    return (
        f"| {stamp} | {provenance.git_sha} | {provenance.label} | "
        f"{prof.get('tps', 0.0):.1f} | {prof.get('peak_rss_gb', 0.0):.2f} | {total(prof)} | "
        f"{prod.get('tps', 0.0):.1f} | {prod.get('peak_rss_gb', 0.0):.2f} | {total(prod)} |"
    )


def _append_log_row(row: str) -> None:
    with OPTIMIZATION_LOG.open("a") as f:
        f.write(row + "\n")


def _terms(result: ScoreResult, tps: float, peak_rss_gb: float) -> dict:
    return {
        "tps": tps,
        "peak_rss_gb": peak_rss_gb,
        "s_total": result.s_total,
        "s_perf": result.s_perf,
        "s_eff": result.s_eff,
        "disqualified": result.disqualified,
        "reason": result.disqualification_reason,
    }


def _prepare(args) -> tuple[Path, Path, Path | None]:
    """Bootstrap the profiler, resolve the model, synthesize the submission dir."""
    from runtime.config import RuntimeConfig
    from runtime.models import resolve_model

    binary = install.ensure_profiler()
    model = resolve_model(RuntimeConfig())
    submission_dir = submission.synthesize(model, docker_image=args.docker_image)
    return binary, submission_dir, find_llama_bench_dir()


def _run_product(args):
    from bench.profile import run_product_path

    return run_product_path(base_url=args.base_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="muta-autotest", description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--docker-image", default=None)
    parser.add_argument(
        "--skip-product", action="store_true", help="run only the officially scored path"
    )
    parser.add_argument(
        "--no-log", action="store_true", help="do not append a row to optimization-log.md"
    )
    args = parser.parse_args(argv)

    provenance = capture_provenance()
    print(
        f"host: {provenance.system}/{provenance.machine} "
        f"sha={provenance.git_sha} [{provenance.label}]"
    )
    if provenance.label == "dev_host_provisional":
        print("  note: dev-host numbers are provisional; report figures come from the x86 box")

    try:
        binary, submission_dir, extra_path = _prepare(args)
    except Exception as e:  # noqa: BLE001 — every prepare failure is already self-describing
        print(f"error: {e}", file=sys.stderr)
        return 2

    if extra_path is None:
        print(
            "error: llama-bench not found — the profiler resolves it on PATH only.\n"
            "  fix: `make build` (container) or `brew install llama.cpp` (dev)",
            file=sys.stderr,
        )
        return 2

    output = ARTIFACT_DIR / "submission.json"
    try:
        data = run_official(binary, submission_dir, output, extra_path=extra_path)
    except AutotestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not params_match(data):
        print(
            "error: GGUF fraud check failed — the claimed parameter estimate does not match "
            "the model header. This is fatal at audit, so it is fatal here.",
            file=sys.stderr,
        )
        return 3

    profiler_run = from_profiler_json(data)
    profiler_score = score_run(profiler_run, accuracy=ASSUMED_ACCURACY, label="profiler")
    print(f"\nscored path   {profiler_score.summary()}")

    scored = {"profiler": _terms(profiler_score, profiler_run.tps_actual, profiler_run.peak_rss_gb)}
    exit_code = 0

    if not args.skip_product:
        product = _run_product(args)
        if product is not None:
            product_score = score_run(product.run, accuracy=ASSUMED_ACCURACY, label="product")
            print(f"product path  {product_score.summary()}")
            scored["product"] = _terms(
                product_score, product.run.tps_actual, product.run.peak_rss_gb
            )
            if product_score.disqualified or product_score.over_budget:
                exit_code = 1
            # Not a clean "overhead" figure, and must not be reported as one: the profiler
            # measures (profiler + llama-bench) while this measures (gateway + llama-server).
            # Different trees running different workloads — the useful signal is the SIGN and
            # the magnitude, i.e. whether the product path is drifting away from the number
            # the audit will reproduce.
            delta_ram = product.run.peak_rss_gb - profiler_run.peak_rss_gb
            print(
                f"\npeak RSS, product vs scored tree: {delta_ram:+.2f} GB "
                "(different trees — a widening gap is the signal, not the absolute value)"
            )

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance.__dict__,
        "assumed_accuracy": ASSUMED_ACCURACY,
        "tps_max_provenance": "provisional_reference",
        "scored": scored,
    }
    RUNS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_JSONL.open("a") as f:
        f.write(json.dumps(record) + "\n")

    if not args.no_log:
        _append_log_row(log_row(scored, provenance))
        print(f"\nappended a row to {OPTIMIZATION_LOG.name}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

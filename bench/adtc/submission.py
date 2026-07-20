"""Synthesize the submission directory the profiler expects.

Split by lifetime, not by convenience:

- **Checked in** (`bench/submission/metadata.json`): the durable Gate 1 claims — team, domain,
  submitter, test prompts. A competition deliverable, so it must be reviewable and diffable.
- **Generated** (`bench/.artifacts/submission/`): the volatile parts — the model file, the
  `_runtime` block, and `parameters_estimate`.

`parameters_estimate` is derived from the actual GGUF header rather than hand-written because
upstream `cli.py` fraud-checks it (`gguf.fraud_check(claimed, actual)`) and writes the verdict
into the report. A stale string after a model swap is a fraud-check failure in a competition
artifact. Deriving it makes that class of failure unreachable.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from bench.adtc.install import ProfilerUnavailable, run_python

_BENCH = Path(__file__).resolve().parents[1]
METADATA_PATH = _BENCH / "submission" / "metadata.json"
ARTIFACT_DIR = _BENCH / ".artifacts"


class SubmissionError(RuntimeError):
    """The submission directory could not be synthesized."""


def format_parameter_estimate(params_count: int | None, *, fallback: str = "unknown") -> str:
    """Render a param count as the string upstream's fraud check parses.

    Upstream `fraud_check` is one-sided — `actual_params <= claimed * 1.20` — so understating
    fails while overstating passes. Round **up** so a derived estimate can never fail.

    Not every GGUF carries `general.parameter_count` — the Unsloth Qwen3-0.6B build does not,
    verified 2026-07-20. When the header is silent, `fallback` (the checked-in claim) is used
    rather than emitting "unknown" into a competition artifact. The fraud check waves both
    through, but only one of them is a real claim.
    """
    if params_count is None:
        return fallback
    if params_count >= 1_000_000_000:
        return f"{math.ceil(params_count / 1e8) / 10:.1f}B"
    return f"{math.ceil(params_count / 1e6):.0f}M"


def read_gguf_metadata(model_path: Path) -> dict:
    """Read the GGUF header using upstream's own parser, inside the profiler venv.

    Reusing their parser rather than porting one guarantees our claimed estimate is derived
    from exactly the number their fraud check compares against. Returns {} if the profiler is
    not bootstrapped — the caller degrades to "unknown", which fraud_check waves through.
    """
    code = (
        "import json\n"
        "from pathlib import Path\n"
        "from adtc_profiler import gguf\n"
        f"print(json.dumps(gguf.extract_metadata(Path({str(model_path)!r}))))\n"
    )
    try:
        return json.loads(run_python(code))
    except (ProfilerUnavailable, json.JSONDecodeError):
        return {}


def test_prompts() -> list[dict]:
    """The two prompts from the checked-in metadata (the schema allows exactly two)."""
    return json.loads(METADATA_PATH.read_text())["test_prompts"]


def synthesize(
    model_path: Path,
    *,
    dest: Path = ARTIFACT_DIR / "submission",
    docker_image: str | None = None,
) -> Path:
    """Build the submission directory and return its path."""
    if not model_path.is_file():
        raise SubmissionError(
            f"model not found at {model_path}. Run `make model` or `./run.sh` to provision it."
        )
    if not METADATA_PATH.is_file():
        raise SubmissionError(f"checked-in claims missing at {METADATA_PATH}")

    meta = json.loads(METADATA_PATH.read_text())

    header = read_gguf_metadata(model_path)
    model_block = meta.setdefault("model", {})
    model_block["parameters_estimate"] = format_parameter_estimate(
        header.get("params_count"), fallback=model_block.get("parameters_estimate", "unknown")
    )
    meta["_runtime"] = {"model_path": "model.gguf"}
    if docker_image:
        meta["_runtime"]["docker_image"] = docker_image

    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "model.gguf"
    if target.exists():
        target.unlink()
    try:
        # Hardlink so a 400 MB GGUF is not copied on every run; fall back across devices.
        target.hardlink_to(model_path)
    except (OSError, AttributeError):
        shutil.copy2(model_path, target)

    (dest / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    return dest

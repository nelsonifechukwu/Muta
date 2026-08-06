"""Runtime configuration. All fields overridable via `MUTA_RT_*` env vars or a local `.env`.

Defaults target the ROADMAP smoke fixture: Qwen3-0.6B at Q4_K_M (~400 MB), the Unsloth
Dynamic 2.0 GGUF (ROADMAP 15/18 Jul), CPU-only to match the deployment target.
"""

from __future__ import annotations

import functools
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@functools.cache
def darwin_performance_cores() -> int | None:
    """Physical P-core count on Apple silicon, None anywhere else (incl. Intel Macs).

    Native decode is bandwidth-bound and barrier-synchronized: one thread scheduled onto
    an efficiency core stalls the whole step. Measured on the M2 Pro dev host (RESULTS.md
    2026-08-01): engine-default threading fell as low as 6.4 tok/s under ambient load
    (max 23.5 across identical warm probes) and -t 10 collapsed to 4.4; -t 6 -tb 6 gave
    the sweep's best maxes (29.6-31.1) and, combined with --kv-unified, its most stable
    runs (floor 20.5 under the same load). Prefill also LOSES from E-cores here
    (-tb 8/10 measured 74/61 vs 97 prefill tok/s at -tb 6).
    """
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return int(out.stdout.strip()) or None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class RuntimeConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MUTA_RT_", env_file=".env", extra="ignore")

    # --- Model provisioning -----------------------------------------------------------
    # "local": use a GGUF already in model_dir. "hf": download from hf_repo/hf_file.
    # Either way resolution yields a *local* path — the deploy target is offline.
    model_source: Literal["local", "hf"] = "local"
    model_dir: Path = Path("models/Qwen3-0.6B")
    model_file: str = "Qwen3-0.6B-Q4_K_M.gguf"
    hf_repo: str = "unsloth/Qwen3-0.6B-GGUF"
    hf_file: str = "Qwen3-0.6B-Q4_K_M.gguf"
    base_repo: str = "Qwen/Qwen3-0.6B"  # provenance only (safetensors source of the GGUF)
    # When the local file is missing, fall back to downloading it from HF. Keeps the first
    # run friction-free while defaulting the *source of record* to the local folder.
    auto_download: bool = True

    # --- llama-server -----------------------------------------------------------------
    llama_server_bin: str | None = None  # explicit path; else search build dir then PATH
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    model_alias: str = "qwen3-0.6b"
    n_ctx: int = 4096
    # None -> let llama.cpp choose. On LINUX x86 that default is already the right one:
    # cpu_get_num_math() counts physical cores only (SMT siblings skipped) and on hybrid
    # 12th-gen Intel skips E-cores via CPUID — exactly the regime every measurement here
    # favours — so None is a decision, not an omission. Apple silicon is the exception:
    # llama.cpp has no P/E logic on darwin, hence the explicit derivation below.
    # Compose pins 8/10 for the container via env.
    n_threads: int | None = Field(default_factory=darwin_performance_cores)
    n_gpu_layers: int = 0  # CPU-only target; raise for faster local dev on a GPU box
    # --- engine memory ceilings -------------------------------------------------------
    # b10035 defaults are sized for far bigger boxes. Measured on Qwen3.5-4B (hybrid:
    # ~50 MiB f32 recurrent state per slot and per context checkpoint): -np auto picks 4
    # slots, checkpoints cap at 32/slot and the prompt cache at 8 GiB — RSS drifted
    # 2.9 -> 4.8 GiB in four requests. These four fields bound steady-state RSS.
    # Worst case here: 2 slots x (50 state + 2 x 50 checkpoints) + 256 cache ~= 560 MiB.
    n_parallel: int = 2  # 2, not 1: one warm spare conversation for UI switching
    # Per slot, ~50.25 MiB f32 hybrid state each. 2 keeps two-turn checkpoint restore
    # fully intact (measured native 2026-08-01: turn-2 prompt_n identical to 4-checkpoint
    # runs, accuracy probes 4/4); stressed phys_footprint fell 3519 -> 3137 MiB across
    # the full winner config, and the checkpoint cut alone bounds -201 MiB worst-case.
    # 1 also passed the two-turn probe but leaves no slack for longer dialogs.
    ctx_checkpoints: int = 2
    cache_ram_mib: int = 256  # host-RAM prompt cache (--cache-ram); engine default is 8192
    # Explicit -np N silently flips the engine's unified-KV default OFF, splitting -c
    # across slots (2048 -> 1024/slot, measured: >1024-token prompts got 400s). True
    # restores the sharing `-np auto` had: both slots see the full window, same total KV,
    # and the most stable decode of the 2026-08-01 native sweep. Needs --cache-ram (set).
    kv_unified: bool = True
    n_threads_batch: int | None = Field(
        default_factory=darwin_performance_cores
    )  # prefill; E-cores hurt too
    # Batch geometry + K-cache quantization + thinking cap — previously injected via
    # MUTA_RT_EXTRA_SERVER_ARGS in docker-compose.yml. Small -b/-ub shrink the compute
    # buffers (~31 MiB at -ub 128 on the 4B, measured); q8_0 K halves that side of the
    # attention KV; the reasoning budget force-closes the think phase so the answer
    # always arrives inside a 2048-token context.
    n_batch: int = 512
    n_ubatch: int = 128
    cache_type_k: str = "q8_0"
    # Weight repacking (--no-repack when True). The engine default repacks Q4_0/Q4_K-family
    # tensors into SIMD-friendly ANONYMOUS buffers at load — faster GEMM, but the copy sits
    # on top of the mmap'd file. Measured (RESULTS.md 2026-08-04, M2 native, full suite):
    # phys_footprint 3236 -> 602 MiB with --no-repack, decode NOT measurably worse there.
    # On the 8 GB x86 target the repack copy (~+1.3-2.5 GiB) is the difference between
    # sitting comfortably under the 7 GB disqualification ceiling and courting it; but AVX2
    # repack likely buys more decode on x86 than on the M2, so the default stays False
    # (engine default = repack on) until the x86 A/B lands. Flip with MUTA_RT_NO_REPACK=1.
    no_repack: bool = False
    reasoning_budget: int = 512  # -1 = unrestricted (engine default)
    # Qwen3 is a hybrid-reasoning model. Thinking ON trades tokens/latency for reasoning
    # quality — honoured by llama-server via --jinja (server.py). Set MUTA_RT_ENABLE_THINKING
    # to override. Scoring note: this costs S_perf (slower, more tokens) — verify the accuracy
    # gain is worth it on the target box before trusting it for the report.
    enable_thinking: bool = True
    extra_server_args: list[str] = Field(default_factory=list)
    startup_timeout_s: float = 120.0
    # Per-request client timeout against llama-server. Applies between chunks on streams;
    # generous values are for emulated/dev boxes where time-to-first-token can be long.
    request_timeout_s: float = 120.0
    # Speculative decoding. b10035 gates ALL speculation behind --spec-type (default
    # none): a draft model passed without it is silently ignored (docs/engine-flags.md).
    # "draft-simple" needs draft_model to exist and share the target's vocab — the Qwen3.5
    # family (vocab 248320) rejects Qwen3 drafts (151936). "ngram-simple" is zero-RAM
    # self-speculation from the context; params are the measured tutoring-workload ones.
    #
    # Default is "none" because every CPU measurement this project has taken says so:
    # emulated 6.72 -> 4.77 tok/s at 98.4% draft acceptance, native 30.84 -> 24.72, and the
    # 2026-08-01 retunes (n-max 3 -> 15.75, n-max 8 -> 25.89, ngram-4/12 -> 21.55 against
    # 29.6 draft-off). On CPU the verify pass costs close to full price, so accepting nearly
    # every drafted token still loses — and the draft adds ~520 MiB against an 8 GB box
    # whose ceiling is a disqualification. Flip per-deploy with MUTA_RT_SPEC_TYPE once an
    # x86 A/B says otherwise; "ngram-simple" is the zero-RAM option worth trying first.
    spec_type: Literal["none", "draft-simple", "ngram-simple"] = "none"
    draft_model: Path | None = None
    draft_max: int = 8
    draft_min: int = 1
    # Container mode: the gateway lifespan starts/supervises llama-server itself.
    autostart: bool = False

    # --- Persistent memory ------------------------------------------------------------
    # Postgres DSN. Default points at the compose `db` service as published on the host
    # (127.0.0.1:15432); inside the backend container compose overrides it to db:5432.
    db_url: str = "postgresql://muta:muta@127.0.0.1:15432/muta"
    max_history_messages: int = 20  # multi-turn context window trim (excludes system)

    @property
    def model_path(self) -> Path:
        return self.model_dir / self.model_file

    @property
    def base_url(self) -> str:
        return f"http://{self.server_host}:{self.server_port}"

"""Runtime configuration. All fields overridable via `MUTA_RT_*` env vars or a local `.env`.

Defaults target the ROADMAP smoke fixture: Qwen3-0.6B at Q4_K_M (~400 MB), the Unsloth
Dynamic 2.0 GGUF (ROADMAP 15/18 Jul), CPU-only to match the deployment target.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    n_threads: int | None = None  # None -> let llama.cpp choose
    n_gpu_layers: int = 0  # CPU-only target; raise for faster local dev on a GPU box
    # --- engine memory ceilings -------------------------------------------------------
    # b10035 defaults are sized for far bigger boxes. Measured on Qwen3.5-4B (hybrid:
    # ~50 MiB f32 recurrent state per slot and per context checkpoint): -np auto picks 4
    # slots, checkpoints cap at 32/slot and the prompt cache at 8 GiB — RSS drifted
    # 2.9 -> 4.8 GiB in four requests. These four fields bound steady-state RSS.
    # Worst case here: 2 slots x (50 state + 4 x 50 checkpoints) + 256 cache ~= 750 MiB.
    n_parallel: int = 2  # 2, not 1: one warm spare conversation for UI switching
    ctx_checkpoints: int = 4  # per slot; too low silently breaks multi-turn reuse (T8 verifies)
    cache_ram_mib: int = 256  # host-RAM prompt cache (--cache-ram); engine default is 8192
    n_threads_batch: int | None = None  # prefill threads; None -> engine default
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
    spec_type: Literal["none", "draft-simple", "ngram-simple"] = "draft-simple"
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

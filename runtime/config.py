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
    # Qwen3 is a hybrid-reasoning model; keep thinking OFF for concise tutoring by default.
    enable_thinking: bool = False
    extra_server_args: list[str] = Field(default_factory=list)
    startup_timeout_s: float = 120.0

    # --- Persistent memory ------------------------------------------------------------
    db_path: Path = Path("data/muta.sqlite3")
    max_history_messages: int = 20  # multi-turn context window trim (excludes system)

    @property
    def model_path(self) -> Path:
        return self.model_dir / self.model_file

    @property
    def base_url(self) -> str:
        return f"http://{self.server_host}:{self.server_port}"

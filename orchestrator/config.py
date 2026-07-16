"""Runtime configuration — encodes the dev-vs-deploy topology (ROADMAP A.1/A.2).

`deploy_mode`:
  - "mounted"  → one process; sub-apps reached in-process (the deploy target: two
                 processes total, llama-server + this).
  - "split"    → each sub-app runs standalone on its own port during development; the
                 gateway reaches them over HTTP at the `*_url` addresses below.

All values are overridable via `MUTA_*` env vars or a local `.env`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MUTA_", env_file=".env", extra="ignore")

    deploy_mode: str = "mounted"

    # Upstream inference engine (llama-server) — a separate process either way.
    llama_server_url: str = "http://127.0.0.1:8080"

    # Internal sub-app addresses — only used in split mode.
    math_url: str = "http://127.0.0.1:8101"
    retrieval_url: str = "http://127.0.0.1:8102"
    pedagogy_url: str = "http://127.0.0.1:8103"
    exam_url: str = "http://127.0.0.1:8104"


settings = Settings()

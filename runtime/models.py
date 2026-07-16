"""Model resolution — turn a config into a concrete local GGUF path.

Local folder is the default source of record; Hugging Face is a provisioning convenience
for development. Both converge on a single local file, because the deployment target runs
offline from a flash drive (ROADMAP A.1) — llama-server's own `-hf` puller is deliberately
not used, so nothing depends on network at run time.
"""

from __future__ import annotations

import logging
from pathlib import Path

from runtime.config import RuntimeConfig

log = logging.getLogger("muta.runtime.models")


def resolve_model(cfg: RuntimeConfig) -> Path:
    """Return a local path to the GGUF, downloading from HF if allowed and missing."""
    local = cfg.model_path
    if local.exists():
        log.info("using local model: %s (%.0f MB)", local, local.stat().st_size / 1e6)
        return local

    if cfg.model_source == "hf" or cfg.auto_download:
        log.info("model not found at %s — downloading %s/%s", local, cfg.hf_repo, cfg.hf_file)
        return download_from_hf(cfg)

    raise FileNotFoundError(
        f"Model not found: {local}\n"
        f"  Either place a GGUF there, or set MUTA_RT_MODEL_SOURCE=hf (or "
        f"MUTA_RT_AUTO_DOWNLOAD=true) to pull {cfg.hf_repo}/{cfg.hf_file} from Hugging Face."
    )


def download_from_hf(cfg: RuntimeConfig) -> Path:
    """Download the configured GGUF into model_dir and return its path."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "huggingface_hub is required to download models. Install with "
            "`pip install -e .` (it is a project dependency)."
        ) from e

    cfg.model_dir.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        repo_id=cfg.hf_repo,
        filename=cfg.hf_file,
        local_dir=str(cfg.model_dir),
    )
    resolved = Path(path)
    log.info("downloaded model: %s (%.0f MB)", resolved, resolved.stat().st_size / 1e6)
    return resolved

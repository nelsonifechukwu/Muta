"""Supervise the llama.cpp `llama-server` process.

`llama-server` is the inference service — a separate process exposing an OpenAI-compatible
HTTP API (ROADMAP A.2/A.3). This module locates the binary, launches it against a resolved
model with CPU-appropriate flags, and health-checks it. `ensure()` attaches to an
already-running server instead of starting a second one.

Run standalone:  `python -m runtime.server`  (or `make serve`) — launches and blocks.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from runtime.config import RuntimeConfig
from runtime.models import resolve_model

log = logging.getLogger("muta.runtime.server")

# Search order for the binary when not set explicitly: the container/native build output
# (ROADMAP: runtime/build/bin), then whatever is on PATH (e.g. `brew install llama.cpp`).
_BUILD_BIN = Path(__file__).resolve().parent / "build" / "bin" / "llama-server"


def find_binary(cfg: RuntimeConfig) -> str:
    for candidate in (cfg.llama_server_bin, str(_BUILD_BIN) if _BUILD_BIN.exists() else None):
        if candidate and Path(candidate).exists():
            return candidate
    on_path = shutil.which("llama-server")
    if on_path:
        return on_path
    raise RuntimeError(
        "llama-server not found. Install a llama.cpp build, e.g.\n"
        "  macOS:  brew install llama.cpp\n"
        "  linux/amd64 (target): build in the container (ROADMAP 15 Jul) into runtime/build/bin\n"
        "or set MUTA_RT_LLAMA_SERVER_BIN=/path/to/llama-server."
    )


class LlamaServer:
    def __init__(self, cfg: RuntimeConfig | None = None) -> None:
        self.cfg = cfg or RuntimeConfig()
        self.process: subprocess.Popen | None = None
        self._managed = False
        self._log_fh = None

    @property
    def base_url(self) -> str:
        return self.cfg.base_url

    def build_command(self, model_path: Path) -> list[str]:
        cfg = self.cfg
        cmd = [
            find_binary(cfg),
            "--model", str(model_path),
            "--alias", cfg.model_alias,
            "--host", cfg.server_host,
            "--port", str(cfg.server_port),
            "--ctx-size", str(cfg.n_ctx),
            "--n-gpu-layers", str(cfg.n_gpu_layers),
            "--jinja",  # apply the model's embedded chat template (Qwen3 thinking control)
            # RAM ceilings — see the field comments in runtime/config.py.
            "--parallel", str(cfg.n_parallel),
            "--ctx-checkpoints", str(cfg.ctx_checkpoints),
            "--cache-ram", str(cfg.cache_ram_mib),
            # Explicit --parallel disables the engine's unified-KV default; restore it so
            # slots share the full -c window instead of splitting it (runtime/config.py).
            *(["--kv-unified"] if cfg.kv_unified else []),
            "-b", str(cfg.n_batch),
            "-ub", str(cfg.n_ubatch),
            "--cache-type-k", cfg.cache_type_k,
            "--reasoning-budget", str(cfg.reasoning_budget),
        ]
        if cfg.n_threads is not None:
            cmd += ["--threads", str(cfg.n_threads)]
        if cfg.n_threads_batch is not None:
            cmd += ["--threads-batch", str(cfg.n_threads_batch)]
        cmd += self._speculation_flags()
        cmd += cfg.extra_server_args
        return cmd

    def _speculation_flags(self) -> list[str]:
        """Flag spellings are the b10035 ones (--spec-type framework; the old
        --draft-max/--draft-min were REMOVED upstream and hard-fail at startup)."""
        cfg = self.cfg
        if cfg.spec_type == "draft-simple":
            if not (cfg.draft_model and Path(cfg.draft_model).is_file()):
                # Degradation, not error: the stack must boot without the draft.
                log.info("spec_type=draft-simple but no draft model at %s — speculation off", cfg.draft_model)
                return []
            return [
                "--spec-type", "draft-simple",
                "--spec-draft-model", str(cfg.draft_model),
                "--spec-draft-n-max", str(cfg.draft_max),
                "--spec-draft-n-min", str(cfg.draft_min),
                "--spec-draft-p-min", "0.75",
            ]
        if cfg.spec_type == "ngram-simple":
            # Engine defaults (N=12) never drafted on tutoring turns; N=4/M=12 measured
            # 12-22% token acceptance at zero RAM cost (docs/engine-flags.md).
            return [
                "--spec-type", "ngram-simple",
                "--spec-ngram-simple-size-n", "4",
                "--spec-ngram-simple-size-m", "12",
            ]
        return []

    def is_up(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=2.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def start(self, log_file: str | Path | None = None) -> "LlamaServer":
        """Resolve the model, launch llama-server, block until /health is green.

        With ``log_file`` the engine's (noisy) stdout/stderr go to that file instead of the
        console — keeps REPL/demo output clean and gives the profiler a log to parse."""
        model_path = resolve_model(self.cfg)
        cmd = self.build_command(model_path)
        log.info("launching: %s", " ".join(cmd))
        out = None
        if log_file is not None:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            self._log_fh = open(log_file, "w")
            out = self._log_fh
        self.process = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT if out else None)
        self._managed = True
        self._wait_until_ready()
        return self

    def ensure(self, log_file: str | Path | None = None) -> tuple["LlamaServer", bool]:
        """Attach if a server is already up; otherwise start one. Returns (self, managed)."""
        if self.is_up():
            log.info("attaching to existing llama-server at %s", self.base_url)
            self._managed = False
            return self, False
        self.start(log_file=log_file)
        return self, True

    def _wait_until_ready(self) -> None:
        deadline = self.cfg.startup_timeout_s
        waited = 0.0
        step = 0.5
        while waited < deadline:
            if self.process and self.process.poll() is not None:
                raise RuntimeError(f"llama-server exited early with code {self.process.returncode}")
            if self.is_up():
                log.info("llama-server ready at %s", self.base_url)
                return
            time.sleep(step)
            waited += step
        raise TimeoutError(f"llama-server not ready after {deadline:.0f}s")

    def stop(self) -> None:
        if self.process and self._managed and self.process.poll() is None:
            log.info("stopping llama-server")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if self._log_fh is not None:
            self._log_fh.close()
            self._log_fh = None

    def __enter__(self) -> "LlamaServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = RuntimeConfig()
    if "--print-cmd" in sys.argv:
        print(" ".join(LlamaServer(cfg).build_command(cfg.model_path)))
        return 0
    server = LlamaServer(cfg)
    server.start()
    print(f"\nllama-server running at {server.base_url}  (Ctrl-C to stop)\n")
    try:
        assert server.process is not None
        server.process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

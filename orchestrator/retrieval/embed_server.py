"""Gateway-managed bge-small sidecar for learner-document retrieval.

The bundled model pack already ships `models/embed/bge-small-en-v1.5-q8_0.gguf`; until now
uploaded documents were indexed with a hashed bag-of-words. This manager follows the
CORE-VISION pattern (runtime/vision.py): spawn on first use, health-gate, reap after idle.
bge-small is ~35 MB of weights, so an idle sidecar costs little, but it is still reaped:
nothing should hold memory the tutor might need when no document is being prepared or asked.

Failure is never a learner-facing error. `EmbeddingUnavailable` lets the resource service
fall back to lexical scoring (queries) or the hashing index (preparation).
"""

from __future__ import annotations

import contextlib
import logging
import os
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

import httpx

from orchestrator.retrieval.embedder import ServerEmbedder
from runtime.profiles import BundlePaths, embed_command

log = logging.getLogger("muta.retrieval.embed_server")

EMBED_MODEL_ALIAS = "bge-small-en-v1.5-q8_0"
IDLE_TTL_SECONDS = 300.0
STARTUP_TIMEOUT_SECONDS = 30.0
#: After a failed start, report unavailable at once for this long instead of making every
#: question wait out another start attempt (questions then score lexically).
FAILURE_BACKOFF_SECONDS = 300.0
#: bge-small reads at most 512 tokens. Chunks are ~900 characters plus a short § prefix; the
#: cap only bites on pathological input and keeps dense text (formulas, code) in bounds.
MAX_EMBED_CHARS = 1200
BATCH = 16


class EmbeddingUnavailable(RuntimeError):
    """The sidecar could not be started or did not answer; callers degrade, never fail."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _threads() -> int:
    return max(1, min(4, (os.cpu_count() or 2) // 2))


@dataclass
class EmbeddingManager:
    paths: BundlePaths = field(default_factory=BundlePaths.from_env)
    ttl_seconds: float = IDLE_TTL_SECONDS
    startup_timeout_s: float = STARTUP_TIMEOUT_SECONDS
    clock: Callable[[], float] = time.monotonic

    process: subprocess.Popen | None = field(default=None, init=False)
    port: int | None = field(default=None, init=False)
    last_used: float | None = field(default=None, init=False)
    spawns: int = field(default=0, init=False)
    failed_at: float | None = field(default=None, init=False)
    _active: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _active_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def available(self) -> bool:
        """Whether a bge model is installed at all (cheap; no process is started)."""
        try:
            return self.paths.embed_model.is_file()
        except (FileNotFoundError, RuntimeError):
            return False

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def api_key(self) -> str | None:
        """embed_command passes the bundle's API key to the server when one exists."""
        try:
            key_file = self.paths.api_key_file
            return key_file.read_text().strip() if key_file.is_file() else None
        except OSError:
            return None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def ensure(self) -> str:
        with self._lock:
            if self.running:
                self.last_used = self.clock()
                return self.base_url
            if (
                self.failed_at is not None
                and self.clock() - self.failed_at < FAILURE_BACKOFF_SECONDS
            ):
                raise EmbeddingUnavailable("embedding server failed to start recently")
            try:
                self._spawn()
            except EmbeddingUnavailable:
                self.failed_at = self.clock()
                raise
            self.failed_at = None
            self.last_used = self.clock()
            return self.base_url

    def _spawn(self) -> None:
        try:
            port = _free_port()
            invocation = embed_command(
                self.paths, port_number=port, ctx=1024, slots=2, threads=_threads()
            )
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            raise EmbeddingUnavailable(f"embedding model is not installed: {exc}") from exc
        with contextlib.suppress(OSError):
            self.paths.log_dir.mkdir(parents=True, exist_ok=True)
        log.info("spawning document embedder on :%s", port)
        try:
            self.process = subprocess.Popen(
                invocation.argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except OSError as exc:
            raise EmbeddingUnavailable(f"embedding server could not start: {exc}") from exc
        self.port = port
        self.spawns += 1
        started = self.clock()
        process = self.process
        while self.clock() - started < self.startup_timeout_s:
            if process.poll() is not None:
                self.process = None
                raise EmbeddingUnavailable(
                    f"embedding server exited during startup (code {process.returncode})"
                )
            try:
                if httpx.get(f"{self.base_url}/health", timeout=1.0).status_code == 200:
                    log.info("document embedder ready in %.1fs", self.clock() - started)
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        self.stop()
        raise EmbeddingUnavailable("embedding server did not become ready in time")

    @contextlib.contextmanager
    def in_use(self) -> Iterator[str]:
        url = self.ensure()
        with self._active_lock:
            self._active += 1
        try:
            yield url
        finally:
            with self._active_lock:
                self._active -= 1
                self.last_used = self.clock()

    def reap_if_idle(self) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._active or not self.running or self.last_used is None:
                return False
            if self.clock() - self.last_used < self.ttl_seconds:
                return False
            log.info("reaping idle document embedder")
            self.stop()
            return True
        finally:
            self._lock.release()

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@dataclass
class ManagedServerEmbedder:
    """bge-small through the managed sidecar; same identity as the classroom ServerEmbedder."""

    manager: EmbeddingManager
    model: str = EMBED_MODEL_ALIAS
    dimensions: int = 384
    timeout: float = 60.0

    @property
    def identity(self) -> str:
        return f"server:{self.model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        try:
            with self.manager.in_use() as url:
                client = ServerEmbedder(
                    base_url=url,
                    model=self.model,
                    api_key=self.manager.api_key(),
                    timeout=self.timeout,
                )
                for start in range(0, len(texts), BATCH):
                    batch = [text[:MAX_EMBED_CHARS] for text in texts[start : start + BATCH]]
                    try:
                        vectors.extend(client.embed(batch))
                    except httpx.HTTPStatusError:
                        # Dense text (LaTeX, non-Latin scripts) can exceed bge's 512 tokens
                        # within the character cap. Retry items alone, shorter, rather than
                        # demote the whole document to the hashing index.
                        vectors.extend(self._embed_one(client, text) for text in batch)
        except EmbeddingUnavailable:
            raise
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise EmbeddingUnavailable(f"embedding request failed: {exc}") from exc
        if len(vectors) != len(texts):
            raise EmbeddingUnavailable("the embedding service returned an incomplete result")
        return vectors

    @staticmethod
    def _embed_one(client: ServerEmbedder, text: str) -> list[float]:
        for limit in (MAX_EMBED_CHARS // 2, MAX_EMBED_CHARS // 4, 160):
            try:
                return client.embed([text[:limit]])[0]
            except httpx.HTTPStatusError:
                continue
        raise EmbeddingUnavailable("a passage could not be embedded at any length")

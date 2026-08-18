"""Versioned local model registry and hash-verified engine hot switching.

The browser selects an opaque catalog id; it never supplies a path.  The manager keeps one
llama-server resident, serializes replacement, and rolls back if a candidate cannot start.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from runtime.config import RuntimeConfig
from runtime.server import LlamaServer

log = logging.getLogger("muta.runtime.model_catalog")


class ModelSwitchError(RuntimeError):
    """A requested model cannot be selected without risking the running engine."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    kind: Literal["local", "cloud"]
    description: str
    path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    arc_easy: float | None = None
    audit_proxy_tps: float | None = None
    recommended: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ModelSpec:
        spec = cls(**raw)
        if spec.kind == "local":
            if not spec.path or not spec.sha256 or len(spec.sha256) != 64:
                raise ValueError(f"local model {spec.id!r} needs path and sha256")
            candidate = Path(spec.path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"model {spec.id!r} path must stay below TUTOR_ROOT")
        return spec


def load_catalog(root: Path, path: Path | None = None) -> tuple[ModelSpec, ...]:
    catalog_path = path or root / "runtime" / "model-catalog.json"
    if path is None and not catalog_path.is_file():
        # Tests and editable installs may deliberately point TUTOR_ROOT at an empty data root;
        # the versioned registry still lives alongside this source tree.
        catalog_path = Path(__file__).resolve().with_name("model-catalog.json")
    raw = json.loads(catalog_path.read_text())
    if raw.get("schema_version") != 1:
        raise ValueError(f"unsupported model catalog schema: {raw.get('schema_version')!r}")
    specs = tuple(ModelSpec.from_dict(item) for item in raw["models"])
    ids = [spec.id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate model id in catalog")
    return specs


class ModelManager:
    """The process-wide engine owner used by the supervisor and `/v1/models/select`."""

    def __init__(
        self,
        cfg: RuntimeConfig,
        *,
        root: Path,
        log_file: Path,
        catalog_path: Path | None = None,
        server_factory: Callable[[RuntimeConfig], LlamaServer] = LlamaServer,
    ) -> None:
        self.cfg = cfg
        self.root = root.resolve()
        self.log_file = log_file
        self.specs = load_catalog(self.root, catalog_path)
        self._by_id = {spec.id: spec for spec in self.specs}
        self._server_factory = server_factory
        self._server = server_factory(cfg)
        self._lock = threading.RLock()
        self._switch_lock = threading.Lock()
        self._switch_done = threading.Event()
        self._switch_done.set()
        self._hash_lock = threading.Lock()
        self._switching = False
        self._planned_exits: set[int] = set()
        self._hash_cache: dict[tuple[Path, int, int, int], str] = {}
        self._active_id = self._match_config(cfg)

    @property
    def process(self):
        with self._lock:
            return self._server.process

    def ensure(self, log_file: Path | None = None) -> tuple[ModelManager, bool]:
        """Supervisor-compatible ensure that preserves ownership after an API switch."""
        while True:
            self._switch_done.wait()
            with self._lock:
                # The Event can be observed just before switch() clears it. Re-check the
                # state under the lock rather than starting a second child in that gap.
                if self._switching:
                    continue
                proc = self._server.process
                if proc is not None and proc.poll() is None and self._server.is_up():
                    return self, True
                # A catalog-backed default gets the same integrity gate as an interactive
                # selection. Never launch a same-size but hash-wrong "winner" merely because
                # its path matched the config.
                if self._active_id is not None:
                    self._verified_path(self._by_id[self._active_id])
                _, managed = self._server.ensure(log_file=log_file or self.log_file)
                return self, managed

    def stop(self) -> None:
        # Shutdown cannot race a replacement and accidentally leave its new child behind.
        with self._switch_lock, self._lock:
            proc = self._server.process
            if proc is not None:
                self._planned_exits.add(id(proc))
            self._server.stop()

    def consume_planned_exit(self, proc: object) -> bool:
        with self._lock:
            key = id(proc)
            if key in self._planned_exits:
                self._planned_exits.remove(key)
                return True
            return False

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_id": self._active_id,
                "switching": self._switching,
                "models": [self._status_for(spec) for spec in self.specs],
            }

    def switch(self, model_id: str) -> dict[str, Any]:
        if not self._switch_lock.acquire(blocking=False):
            raise ModelSwitchError("another model switch is already in progress")
        marked_switching = False
        try:
            with self._lock:
                spec = self._by_id.get(model_id)
                if spec is None:
                    raise ModelSwitchError("unknown model id")
                if spec.kind != "local":
                    raise ModelSwitchError("cloud models are unavailable in offline mode")
                if model_id == self._active_id and self._server.is_up():
                    return self.status()
                old_server = self._server
                old_cfg = self.cfg
                old_id = self._active_id
                self._switching = True
                self._switch_done.clear()
                marked_switching = True

            model_path = self._verified_path(spec)
            with self._lock:
                old_proc = old_server.process
                if old_proc is not None:
                    self._planned_exits.add(id(old_proc))
            old_server.stop()

            new_cfg = self._config_for(old_cfg, model_path)
            new_server = self._server_factory(new_cfg)
            try:
                new_server.start(log_file=self.log_file)
            except Exception as exc:
                new_server.stop()
                log.exception("model %s failed to start; restoring %s", model_id, old_id)
                rollback = self._server_factory(old_cfg)
                try:
                    rollback.start(log_file=self.log_file)
                except Exception as rollback_exc:
                    rollback.stop()
                    with self._lock:
                        self._server = rollback
                        self.cfg = old_cfg
                        self._active_id = old_id
                    raise ModelSwitchError(
                        f"{model_id} failed and the previous engine could not be restored"
                    ) from rollback_exc
                with self._lock:
                    self._server = rollback
                    self.cfg = old_cfg
                    self._active_id = old_id
                raise ModelSwitchError(f"{model_id} failed to start; previous model restored") from exc

            with self._lock:
                self._server = new_server
                self.cfg = new_cfg
                self._active_id = model_id
            log.info("active model switched to %s", model_id)
        finally:
            if marked_switching:
                with self._lock:
                    self._switching = False
                    self._switch_done.set()
            self._switch_lock.release()
        return self.status()

    def _match_config(self, cfg: RuntimeConfig) -> str | None:
        configured = cfg.model_dir / cfg.model_file
        if not configured.is_absolute():
            configured = self.root / configured
        configured = configured.resolve()
        for spec in self.specs:
            if spec.kind == "local" and self._path_for(spec) == configured:
                return spec.id
        return None

    def _path_for(self, spec: ModelSpec) -> Path:
        assert spec.path is not None
        path = (self.root / spec.path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ModelSwitchError("catalog model path escaped TUTOR_ROOT")
        return path

    def _verified_path(self, spec: ModelSpec) -> Path:
        path = self._path_for(spec)
        try:
            if not path.is_file():
                raise ModelSwitchError(f"{spec.label} is not installed")
            stat = path.stat()
            if spec.size_bytes is not None and stat.st_size != spec.size_bytes:
                raise ModelSwitchError(f"{spec.label} has the wrong byte size")
            key = (path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            with self._hash_lock:
                digest = self._hash_cache.get(key)
                if digest is None:
                    h = hashlib.sha256()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                            h.update(chunk)
                    digest = h.hexdigest()
                    self._hash_cache[key] = digest
        except OSError as exc:
            raise ModelSwitchError(f"{spec.label} cannot be read") from exc
        if digest != spec.sha256:
            raise ModelSwitchError(f"{spec.label} failed SHA-256 verification")
        return path

    def _status_for(self, spec: ModelSpec) -> dict[str, Any]:
        reason = None
        available = False
        if spec.kind == "cloud":
            reason = "Unavailable offline"
        else:
            try:
                self._verified_path(spec)
                available = True
            except ModelSwitchError as exc:
                reason = str(exc)
        return {
            "id": spec.id,
            "label": spec.label,
            "kind": spec.kind,
            "description": spec.description,
            "available": available,
            "active": spec.id == self._active_id,
            "disabled_reason": reason,
            "size_bytes": spec.size_bytes,
            "arc_easy": spec.arc_easy,
            "audit_proxy_tps": spec.audit_proxy_tps,
            "recommended": spec.recommended,
        }

    @staticmethod
    def _config_for(cfg: RuntimeConfig, model_path: Path) -> RuntimeConfig:
        return cfg.model_copy(
            update={
                "model_source": "local",
                "model_dir": model_path.parent,
                "model_file": model_path.name,
                "auto_download": False,
            }
        )

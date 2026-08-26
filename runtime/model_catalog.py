"""Versioned local model registry and hash-verified engine hot switching.

The browser selects an opaque catalog id; it never supplies a path.  The manager keeps one
llama-server resident, serializes replacement, and rolls back if a candidate cannot start.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from runtime.config import RuntimeConfig
from runtime.gguf import GGUFError, read_metadata
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
    mmproj_path: str | None = None
    mmproj_sha256: str | None = None
    mmproj_size_bytes: int | None = None
    user_added: bool = False
    file_mtime_ns: int | None = None
    file_ctime_ns: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ModelSpec:
        spec = cls(**raw)
        if spec.kind == "local":
            if not spec.path or not spec.sha256 or len(spec.sha256) != 64:
                raise ValueError(f"local model {spec.id!r} needs path and sha256")
            candidate = Path(spec.path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"model {spec.id!r} path must stay below TUTOR_ROOT")
            projector_fields = (spec.mmproj_path, spec.mmproj_sha256, spec.mmproj_size_bytes)
            if any(value is not None for value in projector_fields):
                if not all(value is not None for value in projector_fields):
                    raise ValueError(
                        f"model {spec.id!r} projector needs path, sha256 and size_bytes"
                    )
                projector = Path(str(spec.mmproj_path))
                if projector.is_absolute() or ".." in projector.parts:
                    raise ValueError(f"model {spec.id!r} projector path must stay below TUTOR_ROOT")
                if len(str(spec.mmproj_sha256)) != 64:
                    raise ValueError(f"model {spec.id!r} projector needs a sha256")
        return spec


def load_catalog(root: Path, path: Path | None = None) -> tuple[ModelSpec, ...]:
    configured = os.environ.get("MUTA_MODEL_CATALOG_PATH")
    catalog_path = path or (
        Path(configured) if configured else root / "runtime" / "model-catalog.json"
    )
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
        selection_path: Path | None = None,
        server_factory: Callable[[RuntimeConfig], LlamaServer] = LlamaServer,
    ) -> None:
        self.root = root.resolve()
        self.log_file = log_file
        self._catalog_specs = load_catalog(self.root, catalog_path)
        self.specs = self._catalog_specs
        self._by_id = {spec.id: spec for spec in self.specs}
        self._server_factory = server_factory
        self._lock = threading.RLock()
        self._switch_lock = threading.Lock()
        self._switch_done = threading.Event()
        self._switch_done.set()
        self._hash_lock = threading.Lock()
        self._switching = False
        self._planned_exits: set[int] = set()
        self._hash_cache: dict[tuple[Path, int, int, int], str] = {}
        self._custom_spec_cache: dict[tuple[Path, int, int, int], ModelSpec] = {}
        configured_selection = os.environ.get("MUTA_MODEL_SELECTION_PATH")
        self._selection_path = (
            (selection_path or Path(configured_selection)).expanduser().resolve()
            if selection_path is not None or configured_selection
            else None
        )
        self._refresh_custom_models_locked()
        self._active_id = self._match_config(cfg)
        preferred_id = self._load_preferred_model_id()
        if preferred_id is not None:
            preferred = self._by_id.get(preferred_id)
            if preferred is None or preferred.kind != "local":
                log.warning("ignoring unavailable persisted model selection: %s", preferred_id)
            else:
                try:
                    cfg = self._config_for(
                        cfg,
                        self._verified_path(preferred),
                        self._verified_projector_or_none(preferred),
                    )
                except ModelSwitchError as error:
                    log.warning("ignoring invalid persisted model selection %s: %s", preferred_id, error)
                else:
                    self._active_id = preferred_id
        # A native launcher supplies the active text GGUF through RuntimeConfig. Recover the
        # projector from the catalog before the first server instance is constructed, so a
        # capable default is actually launched as multimodal rather than merely labelled so.
        self.cfg = self._with_verified_projector(cfg, self._active_id)
        self._server = server_factory(self.cfg)

    def _load_preferred_model_id(self) -> str | None:
        path = self._selection_path
        if path is None or not path.is_file() or path.is_symlink():
            return None
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            log.warning("ignoring unreadable persisted model selection %s: %s", path, error)
            return None
        model_id = body.get("model_id") if body.get("schema") == 1 else None
        return model_id if isinstance(model_id, str) and model_id else None

    def _persist_preferred_model_id(self, model_id: str | None) -> None:
        path = self._selection_path
        if path is None or model_id is None:
            return
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"schema": 1, "model_id": model_id}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            log.warning("could not persist model selection %s: %s", path, error)

    @property
    def process(self):
        with self._lock:
            return self._server.process

    def ensure(self, log_file: Path | None = None) -> tuple[ModelManager, bool]:
        """Supervisor-compatible ensure that preserves ownership after an API switch."""
        while True:
            self._switch_done.wait()
            with self._lock:
                self._refresh_custom_models_locked()
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
                    spec = self._by_id[self._active_id]
                    self._verified_path(spec)
                    launch_cfg = self._with_verified_projector(self.cfg, self._active_id)
                    if launch_cfg != self.cfg:
                        # Projector integrity may change while the engine is stopped. Rebuild
                        # the not-yet-running supervisor so a corrupt optional file degrades
                        # to text-only instead of being handed to llama-server.
                        self.cfg = launch_cfg
                        self._server = self._server_factory(launch_cfg)
                _, managed = self._server.ensure(log_file=log_file or self.log_file)
                return self, managed

    def stop(self) -> None:
        # Shutdown cannot race a replacement and accidentally leave its new child behind.
        with self._switch_lock, self._lock:
            proc = self._server.process
            if proc is not None:
                self._planned_exits.add(id(proc))
            self._server.stop()

    def prepare_startup(self, cfg: RuntimeConfig) -> RuntimeConfig:
        """Install an authoritative pre-launch model/capacity profile without re-reading prefs.

        Desktop startup first resolves the operator's saved model through this manager, then
        Host-mode planning may choose safer slot limits or a smaller core model. Applying that
        result to the same not-yet-started manager prevents the saved preference from racing or
        undoing the RAM-safety decision.
        """
        with self._switch_lock, self._lock:
            if self._server.process is not None or self._server.is_up():
                raise ModelSwitchError("startup profile cannot change after the engine starts")
            active_id = self._match_config(cfg)
            if active_id is not None:
                spec = self._by_id[active_id]
                self._verified_path(spec)
                cfg = self._with_verified_projector(cfg, active_id)
            self.cfg = cfg
            self._active_id = active_id
            self._server = self._server_factory(cfg)
            return cfg

    def consume_planned_exit(self, proc: object) -> bool:
        with self._lock:
            key = id(proc)
            if key in self._planned_exits:
                self._planned_exits.remove(key)
                return True
            return False

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_custom_models_locked()
            return {
                "active_id": self._active_id,
                "switching": self._switching,
                "n_parallel": self.cfg.n_parallel,
                "n_ctx": self.cfg.n_ctx,
                "models": [self._status_for(spec) for spec in self.specs],
            }

    def runtime_snapshot(self) -> tuple[RuntimeConfig, str | None]:
        """Capture the exact trusted model/profile needed to compensate a later saga step."""
        with self._lock:
            return self.cfg, self._active_id

    def restore_runtime(self, snapshot: tuple[RuntimeConfig, str | None]) -> RuntimeConfig:
        """Restore an internally captured model and capacity in one rollback-safe restart."""
        target_cfg, target_id = snapshot
        if not self._switch_lock.acquire(blocking=False):
            raise ModelSwitchError("another engine change is already in progress")
        marked_switching = False
        try:
            with self._lock:
                if self.cfg == target_cfg and self._active_id == target_id and self._server.is_up():
                    return self.cfg
                current_server = self._server
                current_cfg = self.cfg
                current_id = self._active_id
                self._switching = True
                self._switch_done.clear()
                marked_switching = True
                process = current_server.process
                if process is not None:
                    self._planned_exits.add(id(process))
            current_server.stop()
            restored = self._server_factory(target_cfg)
            try:
                restored.start(log_file=self.log_file)
            except Exception as exc:
                restored.stop()
                rollback = self._server_factory(current_cfg)
                try:
                    rollback.start(log_file=self.log_file)
                except Exception as rollback_exc:
                    rollback.stop()
                    with self._lock:
                        self._server = rollback
                        self.cfg = current_cfg
                        self._active_id = current_id
                    raise ModelSwitchError(
                        "runtime restore failed and the replacement could not be recovered"
                    ) from rollback_exc
                with self._lock:
                    self._server = rollback
                    self.cfg = current_cfg
                    self._active_id = current_id
                raise ModelSwitchError("runtime restore failed; replacement kept running") from exc
            with self._lock:
                self._server = restored
                self.cfg = target_cfg
                self._active_id = target_id
            return target_cfg
        finally:
            if marked_switching:
                with self._lock:
                    self._switching = False
                    self._switch_done.set()
            self._switch_lock.release()

    def reconfigure_capacity(self, *, n_parallel: int, n_ctx: int) -> RuntimeConfig:
        """Restart the current engine with one complete slot/context profile.

        The caller must have closed admission and drained queued/running work. Replacement is
        rollback-safe for the same reason as model switching: a bad high-capacity profile must
        restore the known-good tutor rather than leave the classroom without an engine.
        """
        if n_parallel < 1 or n_ctx < n_parallel:
            raise ModelSwitchError("invalid capacity profile")
        if not self._switch_lock.acquire(blocking=False):
            raise ModelSwitchError("another engine change is already in progress")
        marked_switching = False
        try:
            with self._lock:
                if self.cfg.n_parallel == n_parallel and self.cfg.n_ctx == n_ctx:
                    return self.cfg
                old_server = self._server
                old_cfg = self.cfg
                old_id = self._active_id
                new_cfg = old_cfg.model_copy(update={"n_parallel": n_parallel, "n_ctx": n_ctx})
                self._switching = True
                self._switch_done.clear()
                marked_switching = True
                old_proc = old_server.process
                if old_proc is not None:
                    self._planned_exits.add(id(old_proc))
            old_server.stop()
            replacement = self._server_factory(new_cfg)
            try:
                replacement.start(log_file=self.log_file)
            except Exception as exc:
                replacement.stop()
                log.exception(
                    "capacity profile %s slots/%s ctx failed; restoring %s/%s",
                    n_parallel,
                    n_ctx,
                    old_cfg.n_parallel,
                    old_cfg.n_ctx,
                )
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
                        "capacity change failed and the previous engine could not be restored"
                    ) from rollback_exc
                with self._lock:
                    self._server = rollback
                    self.cfg = old_cfg
                    self._active_id = old_id
                raise ModelSwitchError(
                    "capacity change failed; previous serving profile restored"
                ) from exc
            with self._lock:
                self._server = replacement
                self.cfg = new_cfg
                self._active_id = old_id
            log.info("capacity profile switched to %s slots / %s total context", n_parallel, n_ctx)
            return new_cfg
        finally:
            if marked_switching:
                with self._lock:
                    self._switching = False
                    self._switch_done.set()
            self._switch_lock.release()

    def candidate_config(self, model_id: str) -> RuntimeConfig:
        """Return the verified target-model config without changing the running engine."""
        with self._lock:
            self._refresh_custom_models_locked()
            spec = self._by_id.get(model_id)
            if spec is None:
                raise ModelSwitchError("unknown model id")
            if spec.kind != "local":
                raise ModelSwitchError("cloud models are unavailable in offline mode")
            base = self.cfg
        return self._config_for(
            base,
            self._verified_path(spec),
            self._verified_projector_or_none(spec),
        )

    def switch(
        self,
        model_id: str,
        *,
        n_parallel: int | None = None,
        n_ctx: int | None = None,
        persist_selection: bool = True,
    ) -> dict[str, Any]:
        if not self._switch_lock.acquire(blocking=False):
            raise ModelSwitchError("another model switch is already in progress")
        marked_switching = False
        try:
            with self._lock:
                self._refresh_custom_models_locked()
                spec = self._by_id.get(model_id)
                if spec is None:
                    raise ModelSwitchError("unknown model id")
                if spec.kind != "local":
                    raise ModelSwitchError("cloud models are unavailable in offline mode")
                target_parallel = n_parallel if n_parallel is not None else self.cfg.n_parallel
                target_ctx = n_ctx if n_ctx is not None else self.cfg.n_ctx
                if target_parallel < 1 or target_ctx < target_parallel:
                    raise ModelSwitchError("invalid capacity profile")
                if (
                    model_id == self._active_id
                    and self._server.is_up()
                    and target_parallel == self.cfg.n_parallel
                    and target_ctx == self.cfg.n_ctx
                ):
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

            new_cfg = self._config_for(
                old_cfg,
                model_path,
                self._verified_projector_or_none(spec),
            ).model_copy(update={"n_parallel": target_parallel, "n_ctx": target_ctx})
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
                raise ModelSwitchError(
                    f"{model_id} failed to start; previous model restored"
                ) from exc

            with self._lock:
                self._server = new_server
                self.cfg = new_cfg
                self._active_id = model_id
            if persist_selection:
                self._persist_preferred_model_id(model_id)
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

    def local_model_ids_by_size(self) -> tuple[str, ...]:
        """Verified installed local ids, smallest first, for a RAM-safe fallback search."""
        with self._lock:
            self._refresh_custom_models_locked()
            ordered = sorted(
                (spec for spec in self.specs if spec.kind == "local"),
                key=lambda spec: (spec.size_bytes or 1 << 62, spec.id),
            )
        available: list[str] = []
        for spec in ordered:
            try:
                self._verified_path(spec)
            except ModelSwitchError:
                continue
            available.append(spec.id)
        return tuple(available)

    def wait_until_ready(self, timeout_s: float) -> bool:
        """Wait for the supervisor/model replacement instead of rejecting a learner turn."""
        import time

        deadline = time.monotonic() + max(0.0, timeout_s)
        while time.monotonic() < deadline:
            self._switch_done.wait(timeout=min(0.2, max(0.0, deadline - time.monotonic())))
            with self._lock:
                if not self._switching and self._server.is_up():
                    return True
            time.sleep(0.1)
        return False

    def _custom_model_paths(self) -> tuple[Path, ...]:
        """Regular GGUFs supplied by the operator, never signed catalog dependencies."""
        candidates: set[Path] = set()
        custom_root = self.root / "models" / "custom"
        if custom_root.is_dir():
            candidates.update(
                path for path in custom_root.rglob("*") if path.suffix.lower() == ".gguf"
            )
        # Also accept the literal model-pack root requested by operators. Launchers normalise
        # these into models/custom when installing from release media.
        if self.root.is_dir():
            candidates.update(
                path for path in self.root.iterdir() if path.suffix.lower() == ".gguf"
            )
        catalog_paths = {
            self._path_for(spec)
            for spec in self._catalog_specs
            if spec.kind == "local" and spec.path is not None
        }
        safe: list[Path] = []
        for candidate in sorted(candidates):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or resolved == self.root
                or self.root not in resolved.parents
                or resolved in catalog_paths
            ):
                continue
            safe.append(resolved)
        return tuple(safe)

    @staticmethod
    def _custom_label(path: Path, metadata: Any) -> str:
        raw = metadata.kv.get("general.name") or metadata.kv.get("general.basename")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()[:96]
        label = path.stem.replace("_", " ").replace("-", " ")
        return " ".join(label.split())[:96] or "Custom GGUF"

    def _refresh_custom_models_locked(self) -> None:
        custom: list[ModelSpec] = []
        current_keys: set[tuple[Path, int, int, int]] = set()
        for path in self._custom_model_paths():
            try:
                stat = path.stat()
                size = stat.st_size
                relative = path.relative_to(self.root).as_posix()
            except (GGUFError, OSError, ValueError):
                log.warning("ignoring invalid custom GGUF: %s", path)
                continue
            key = (path, size, stat.st_mtime_ns, stat.st_ctime_ns)
            current_keys.add(key)
            cached = self._custom_spec_cache.get(key)
            if cached is not None:
                custom.append(cached)
                continue
            try:
                metadata = read_metadata(path, max_kv=4096, max_header_bytes=128 * 1024 * 1024)
            except (GGUFError, OSError, ValueError):
                log.warning("ignoring invalid custom GGUF: %s", path)
                continue
            identifier = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20]
            spec = ModelSpec(
                id=f"custom-{identifier}",
                label=self._custom_label(path, metadata),
                kind="local",
                path=relative,
                size_bytes=size,
                description=f"Added locally · {size / 1024**3:.2f} GB · text only.",
                user_added=True,
                file_mtime_ns=stat.st_mtime_ns,
                file_ctime_ns=stat.st_ctime_ns,
            )
            self._custom_spec_cache[key] = spec
            custom.append(spec)
        self._custom_spec_cache = {
            key: spec for key, spec in self._custom_spec_cache.items() if key in current_keys
        }
        self.specs = (*self._catalog_specs, *custom)
        self._by_id = {spec.id: spec for spec in self.specs}

    def _path_for(self, spec: ModelSpec) -> Path:
        assert spec.path is not None
        path = (self.root / spec.path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ModelSwitchError("catalog model path escaped TUTOR_ROOT")
        return path

    def _projector_path_for(self, spec: ModelSpec) -> Path:
        if spec.mmproj_path is None:
            raise ModelSwitchError(f"{spec.label} accepts text only")
        path = (self.root / spec.mmproj_path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ModelSwitchError("catalog projector path escaped TUTOR_ROOT")
        return path

    def _verified_projector(self, spec: ModelSpec) -> Path:
        path = self._projector_path_for(spec)
        assert spec.mmproj_sha256 is not None
        try:
            if not path.is_file():
                raise ModelSwitchError(f"{spec.label} image projector is not installed")
            stat = path.stat()
            if spec.mmproj_size_bytes is not None and stat.st_size != spec.mmproj_size_bytes:
                raise ModelSwitchError(f"{spec.label} image projector has the wrong byte size")
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
            raise ModelSwitchError(f"{spec.label} image projector cannot be read") from exc
        if digest != spec.mmproj_sha256:
            raise ModelSwitchError(f"{spec.label} image projector failed SHA-256 verification")
        return path

    def _verified_projector_or_none(self, spec: ModelSpec) -> Path | None:
        if spec.mmproj_path is None:
            return None
        try:
            return self._verified_projector(spec)
        except ModelSwitchError:
            # Missing/corrupt optional vision data must not make the text model unselectable.
            # `_status_for` exposes the exact reason and image turns fail before admission.
            return None

    def _with_verified_projector(
        self,
        cfg: RuntimeConfig,
        model_id: str | None,
    ) -> RuntimeConfig:
        if model_id is None:
            return cfg
        spec = self._by_id[model_id]
        return cfg.model_copy(update={"mmproj_path": self._verified_projector_or_none(spec)})

    def _verified_path(self, spec: ModelSpec) -> Path:
        path = self._path_for(spec)
        try:
            if path.is_symlink() or not path.is_file():
                raise ModelSwitchError(f"{spec.label} is not installed")
            stat = path.stat()
            if spec.size_bytes is not None and stat.st_size != spec.size_bytes:
                raise ModelSwitchError(f"{spec.label} has the wrong byte size")
            if spec.user_added:
                if (
                    spec.file_mtime_ns != stat.st_mtime_ns
                    or spec.file_ctime_ns != stat.st_ctime_ns
                ):
                    raise ModelSwitchError(f"{spec.label} changed while it was being selected")
                return path
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
        except (OSError, GGUFError) as exc:
            raise ModelSwitchError(f"{spec.label} cannot be read") from exc
        if digest != spec.sha256:
            raise ModelSwitchError(f"{spec.label} failed SHA-256 verification")
        return path

    def _status_for(self, spec: ModelSpec) -> dict[str, Any]:
        reason = None
        image_reason = None
        supports_images = False
        available = False
        if spec.kind == "cloud":
            reason = "Unavailable offline"
        else:
            try:
                self._verified_path(spec)
                available = True
            except ModelSwitchError as exc:
                reason = str(exc)
            if spec.mmproj_path is not None:
                try:
                    self._verified_projector(spec)
                    supports_images = True
                except ModelSwitchError as exc:
                    image_reason = str(exc)
            else:
                image_reason = f"{spec.label} accepts text only"
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
            "user_added": spec.user_added,
            "supports_images": supports_images,
            "image_input_reason": image_reason,
        }

    @staticmethod
    def _config_for(
        cfg: RuntimeConfig,
        model_path: Path,
        mmproj_path: Path | None = None,
    ) -> RuntimeConfig:
        return cfg.model_copy(
            update={
                "model_source": "local",
                "model_dir": model_path.parent,
                "model_file": model_path.name,
                "auto_download": False,
                "mmproj_path": mmproj_path,
            }
        )

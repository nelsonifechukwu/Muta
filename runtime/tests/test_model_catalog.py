"""The local registry must never trade the running engine for an unverified/broken file."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import ClassVar

import pytest

from runtime.config import RuntimeConfig
from runtime.model_catalog import ModelManager, ModelSwitchError, load_catalog


class _Proc:
    def __init__(self) -> None:
        self.alive = True

    def poll(self):
        return None if self.alive else 0


class _Server:
    instances: ClassVar[list[_Server]] = []
    block_model: ClassVar[str | None] = None
    start_entered: ClassVar[threading.Event] = threading.Event()
    release_start: ClassVar[threading.Event] = threading.Event()
    reject_parallel: ClassVar[int | None] = None

    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.process = None
        self._up = False
        self.instances.append(self)

    def is_up(self) -> bool:
        return self._up

    def start(self, log_file=None):
        _ = log_file
        if self.cfg.n_parallel == self.reject_parallel:
            raise RuntimeError("synthetic capacity failure")
        if self.cfg.model_file == "broken.gguf":
            raise RuntimeError("synthetic loader failure")
        if self.cfg.model_file == self.block_model:
            self.start_entered.set()
            assert self.release_start.wait(timeout=5), "test did not release blocked model start"
        self.process = _Proc()
        self._up = True
        return self

    def ensure(self, log_file=None):
        _ = log_file
        if not self._up:
            self.start()
        return self, True

    def stop(self) -> None:
        if self.process is not None:
            self.process.alive = False
        self._up = False
        self.process = None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manager(
    tmp_path: Path,
    *,
    corrupt_two: bool = False,
    corrupt_projector: bool = False,
    start: bool = True,
) -> ModelManager:
    _Server.instances = []
    _Server.block_model = None
    _Server.start_entered = threading.Event()
    _Server.release_start = threading.Event()
    _Server.reject_parallel = None
    one = tmp_path / "one.gguf"
    two = tmp_path / "two.gguf"
    broken = tmp_path / "broken.gguf"
    projector = tmp_path / "one-mmproj.gguf"
    one.write_bytes(b"one")
    two.write_bytes(b"wrong" if corrupt_two else b"two")
    broken.write_bytes(b"broken")
    projector.write_bytes(b"bad" if corrupt_projector else b"projector")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "models": [
                    {
                        "id": "one",
                        "label": "One",
                        "kind": "local",
                        "path": "one.gguf",
                        "sha256": _sha(b"one"),
                        "size_bytes": 3,
                        "description": "first",
                        "mmproj_path": "one-mmproj.gguf",
                        "mmproj_sha256": _sha(b"projector"),
                        "mmproj_size_bytes": 3 if corrupt_projector else 9,
                    },
                    {
                        "id": "two",
                        "label": "Two",
                        "kind": "local",
                        "path": "two.gguf",
                        "sha256": _sha(b"two"),
                        "size_bytes": 3 if not corrupt_two else 5,
                        "description": "second",
                    },
                    {
                        "id": "broken",
                        "label": "Broken",
                        "kind": "local",
                        "path": "broken.gguf",
                        "sha256": _sha(b"broken"),
                        "size_bytes": 6,
                        "description": "loader rejects this",
                    },
                    {
                        "id": "cloud",
                        "label": "Cloud",
                        "kind": "cloud",
                        "description": "offline",
                    },
                ],
            }
        )
    )
    cfg = RuntimeConfig(
        model_dir=tmp_path,
        model_file="one.gguf",
        auto_download=False,
        _env_file=None,
    )
    manager = ModelManager(
        cfg,
        root=tmp_path,
        log_file=tmp_path / "engine.log",
        catalog_path=catalog,
        server_factory=_Server,
    )
    if start:
        manager.ensure()
    return manager


def test_switches_one_local_engine_and_reports_tradeoffs(tmp_path):
    manager = _manager(tmp_path)

    result = manager.switch("two")

    assert result["active_id"] == "two"
    assert result["switching"] is False
    assert sum(server.is_up() for server in _Server.instances) == 1
    assert (
        next(model for model in result["models"] if model["id"] == "cloud")["disabled_reason"]
        == "Unavailable offline"
    )
    active = next(model for model in result["models"] if model["id"] == "two")
    assert active["supports_images"] is False
    assert "text only" in active["image_input_reason"]


def test_verified_projector_is_loaded_for_the_matching_default(tmp_path):
    manager = _manager(tmp_path)

    active = next(model for model in manager.status()["models"] if model["id"] == "one")
    assert active["supports_images"] is True
    assert manager.cfg.mmproj_path == tmp_path / "one-mmproj.gguf"
    assert _Server.instances[0].cfg.mmproj_path == tmp_path / "one-mmproj.gguf"


def test_shipped_4b_front_door_has_its_exact_model_and_projector_pins():
    root = Path(__file__).resolve().parents[2]
    spec = next(item for item in load_catalog(root) if item.id == "qwen3.5-4b-iq4_xs")

    assert spec.path == "models/core/Qwen3.5-4B-IQ4_XS.gguf"
    assert spec.sha256 == "658a9e7e406deb06d0179755e3c14f6a82915a4be4962a2f92a64d948d2e572f"
    assert spec.size_bytes == 2477053088
    assert spec.mmproj_path == "models/core/mmproj-F16.gguf"
    assert spec.mmproj_sha256 == (
        "cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864"
    )
    assert spec.mmproj_size_bytes == 672423616


def test_corrupt_optional_projector_keeps_text_model_available(tmp_path):
    manager = _manager(tmp_path, corrupt_projector=True)

    active = next(model for model in manager.status()["models"] if model["id"] == "one")
    assert active["available"] is True
    assert active["supports_images"] is False
    assert "projector" in active["image_input_reason"]
    assert manager.cfg.mmproj_path is None


def test_model_switch_applies_target_capacity_in_the_same_restart(tmp_path):
    manager = _manager(tmp_path)

    result = manager.switch("two", n_parallel=4, n_ctx=8192)

    assert result["active_id"] == "two"
    assert manager.cfg.n_parallel == 4
    assert manager.cfg.n_ctx == 8192
    assert _Server.instances[-1].cfg.model_file == "two.gguf"
    assert _Server.instances[-1].cfg.n_parallel == 4


def test_runtime_snapshot_restores_arbitrary_previous_model_and_capacity(tmp_path):
    manager = _manager(tmp_path)
    snapshot = manager.runtime_snapshot()
    manager.switch("two", n_parallel=4, n_ctx=8192)

    restored = manager.restore_runtime(snapshot)

    assert restored == snapshot[0]
    assert manager.status()["active_id"] == "one"
    assert manager.cfg.n_parallel == snapshot[0].n_parallel
    assert manager.cfg.n_ctx == snapshot[0].n_ctx
    assert sum(server.is_up() for server in _Server.instances) == 1


def test_failed_model_and_capacity_switch_restores_both(tmp_path):
    manager = _manager(tmp_path)
    original = manager.cfg
    _Server.reject_parallel = 4

    with pytest.raises(ModelSwitchError, match="previous model restored"):
        manager.switch("two", n_parallel=4, n_ctx=8192)

    assert manager.status()["active_id"] == "one"
    assert manager.cfg.n_parallel == original.n_parallel
    assert manager.cfg.n_ctx == original.n_ctx
    assert sum(server.is_up() for server in _Server.instances) == 1


def test_corrupt_hash_is_disabled_without_stopping_current_engine(tmp_path):
    manager = _manager(tmp_path, corrupt_two=True)

    with pytest.raises(ModelSwitchError, match="SHA-256"):
        manager.switch("two")

    assert manager.status()["active_id"] == "one"
    assert sum(server.is_up() for server in _Server.instances) == 1


def test_corrupt_catalog_default_is_rejected_before_first_launch(tmp_path):
    manager = _manager(tmp_path, start=False)
    (tmp_path / "one.gguf").write_bytes(b"bad")  # same byte size, wrong SHA-256

    with pytest.raises(ModelSwitchError, match="SHA-256"):
        manager.ensure()

    assert manager.process is None
    assert all(not server.is_up() for server in _Server.instances)


def test_failed_candidate_start_rolls_back_to_previous_model(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(ModelSwitchError, match="previous model restored"):
        manager.switch("broken")

    assert manager.status()["active_id"] == "one"
    assert manager.process is not None
    assert sum(server.is_up() for server in _Server.instances) == 1


def test_rejects_arbitrary_ids_and_cloud(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(ModelSwitchError, match="unknown model id"):
        manager.switch("../../secret.gguf")
    with pytest.raises(ModelSwitchError, match="unavailable in offline mode"):
        manager.switch("cloud")


def test_status_stays_readable_and_second_switch_is_rejected_while_loading(tmp_path):
    manager = _manager(tmp_path)
    _Server.block_model = "two.gguf"
    failure: list[BaseException] = []

    def run_switch() -> None:
        try:
            manager.switch("two")
        except ModelSwitchError as exc:  # pragma: no cover - asserted below
            failure.append(exc)

    thread = threading.Thread(target=run_switch)
    thread.start()
    assert _Server.start_entered.wait(timeout=5)

    assert manager.status()["switching"] is True
    with pytest.raises(ModelSwitchError, match="already in progress"):
        manager.switch("one")

    _Server.release_start.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert failure == []
    assert manager.status()["active_id"] == "two"


def test_capacity_reconfiguration_restarts_with_complete_profile(tmp_path):
    manager = _manager(tmp_path)

    cfg = manager.reconfigure_capacity(n_parallel=4, n_ctx=8192)

    assert cfg.n_parallel == 4
    assert cfg.n_ctx == 8192
    assert manager.status()["n_parallel"] == 4
    assert manager.status()["n_ctx"] == 8192
    assert manager.status()["active_id"] == "one"
    assert sum(server.is_up() for server in _Server.instances) == 1


def test_failed_capacity_reconfiguration_restores_previous_profile(tmp_path):
    manager = _manager(tmp_path)
    original = manager.cfg
    _Server.reject_parallel = 4

    with pytest.raises(ModelSwitchError, match="previous serving profile restored"):
        manager.reconfigure_capacity(n_parallel=4, n_ctx=8192)

    assert manager.cfg.n_parallel == original.n_parallel
    assert manager.cfg.n_ctx == original.n_ctx
    assert sum(server.is_up() for server in _Server.instances) == 1

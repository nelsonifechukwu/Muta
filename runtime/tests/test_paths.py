from pathlib import Path

from runtime import paths


def _clear(monkeypatch):
    for name in (
        "MUTA_RESOURCE_ROOT",
        "MUTA_DATA_ROOT",
        "MUTA_CACHE_ROOT",
        "TUTOR_ROOT",
        "LOCALAPPDATA",
        "APPDATA",
        "XDG_DATA_HOME",
    ):
        monkeypatch.delenv(name, raising=False)


def test_explicit_desktop_roots_are_independent(monkeypatch, tmp_path):
    resources = tmp_path / "signed-app"
    state = tmp_path / "writable-state"
    cache = tmp_path / "replaceable-cache"
    monkeypatch.setenv("MUTA_RESOURCE_ROOT", str(resources))
    monkeypatch.setenv("MUTA_DATA_ROOT", str(state))
    monkeypatch.setenv("MUTA_CACHE_ROOT", str(cache))

    assert paths.resource_root() == resources.resolve()
    assert paths.data_root() == state.resolve()
    assert paths.cache_root() == cache.resolve()


def test_legacy_tutor_root_keeps_data_subdirectory(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))

    assert paths.resource_root() == tmp_path.resolve()
    assert paths.data_root() == (tmp_path / "data").resolve()


def test_native_desktop_data_locations(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert paths.default_desktop_data_root("darwin") == (
        tmp_path / "Library" / "Application Support" / "Muta"
    )
    assert paths.default_desktop_data_root("win32") == tmp_path / "AppData" / "Local" / "Muta"
    assert paths.default_desktop_data_root("linux") == tmp_path / ".local" / "share" / "muta"


def test_prepare_mutable_roots_never_writes_resource_root(monkeypatch, tmp_path):
    resources = tmp_path / "resources"
    state = tmp_path / "state"
    resources.mkdir()
    monkeypatch.setenv("MUTA_RESOURCE_ROOT", str(resources))
    monkeypatch.setenv("MUTA_DATA_ROOT", str(state))

    paths.prepare_mutable_roots()

    assert sorted(item.name for item in resources.iterdir()) == []
    assert (state / "logs").is_dir()
    assert (state / "kv-slots").is_dir()
    assert (state / "twins").is_dir()
    assert (state / "cache").is_dir()

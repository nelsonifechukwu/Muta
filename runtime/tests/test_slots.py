"""Slot save/restore + snapshot reaper tests (TDD §8.3, T12)."""

from __future__ import annotations

import httpx
import pytest

from runtime.slots import (
    SNAPSHOT_DIR_CAP_BYTES,
    SlotClient,
    SlotError,
    SnapshotReaper,
    snapshot_name,
)


def transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture
def recorded(monkeypatch):
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url, *, params=None, json=None, headers=None, timeout=None):
        calls.append((url, params or {}, json or {}))
        return httpx.Response(200, json={"id_slot": 0, "n_saved": 512}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def test_save_and_restore_address_the_slot_and_the_session_file(recorded):
    client = SlotClient()
    client.save(2, "student-42")
    client.restore(2, "student-42")

    (save_url, save_params, save_body), (restore_url, restore_params, _) = recorded
    assert save_url.endswith("/slots/2") and save_params == {"action": "save"}
    assert save_body == {"filename": "student-42.bin"}
    assert restore_params == {"action": "restore"}
    assert restore_url == save_url


def test_session_ids_are_sanitised_into_filenames():
    assert snapshot_name("class-3/ada okoro") == "class-3_ada_okoro.bin"
    # Dots go too, so a session id can never walk out of the snapshot directory.
    assert snapshot_name("../../etc/passwd") == "______etc_passwd.bin"


def test_api_key_is_sent_when_configured(recorded, monkeypatch):
    seen: dict = {}

    def fake_post(url, *, params=None, json=None, headers=None, timeout=None):
        seen.update(headers or {})
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    SlotClient(api_key="secret").save(0, "s")
    assert seen["Authorization"] == "Bearer secret"


def test_a_failed_save_is_raised_not_swallowed(monkeypatch):
    """A silent save failure means the student's session simply vanishes at resume — the
    caller has to know so it can fall back to a summary re-prefill."""

    def fake_post(url, **_kw):
        return httpx.Response(507, text="disk full", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(SlotError, match="507"):
        SlotClient().save(1, "s")


def test_a_network_error_is_wrapped(monkeypatch):
    def fake_post(url, **_kw):
        raise httpx.ConnectError("no server")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(SlotError, match="slot save failed"):
        SlotClient().save(1, "s")


def test_slot_state_is_readable(monkeypatch):
    def fake_get(url, **_kw):
        return httpx.Response(200, json=[{"id": 0, "state": 1}], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert SlotClient().slots() == [{"id": 0, "state": 1}]


# --- reaper ------------------------------------------------------------------------------


def make_snapshots(directory, sizes: dict[str, int], *, base_atime: float = 1_000_000.0):
    import os

    directory.mkdir(parents=True, exist_ok=True)
    for i, (name, size) in enumerate(sizes.items()):
        path = directory / snapshot_name(name)
        path.write_bytes(b"\x00" * size)
        os.utime(path, (base_atime + i, base_atime + i))  # oldest first
    return directory


def test_reaper_is_a_no_op_under_the_cap(tmp_path):
    directory = make_snapshots(tmp_path / "kv-slots", {"a": 1000, "b": 1000})
    assert SnapshotReaper(directory, cap_bytes=10_000).reap() == []
    assert len(list(directory.glob("*.bin"))) == 2


def test_reaper_evicts_least_recently_used_first(tmp_path):
    directory = make_snapshots(tmp_path / "kv-slots", {"oldest": 1000, "middle": 1000, "newest": 1000})
    removed = SnapshotReaper(directory, cap_bytes=2000).reap()
    assert [p.name for p in removed] == ["oldest.bin"]
    assert SnapshotReaper(directory, cap_bytes=2000).total_bytes() == 2000


def test_live_sessions_are_protected_from_eviction(tmp_path):
    """Evicting the snapshot of a student who is mid-answer converts a cheap restore into a
    cold start for the one person actively waiting."""
    directory = make_snapshots(tmp_path / "kv-slots", {"oldest": 1000, "middle": 1000, "newest": 1000})
    removed = SnapshotReaper(directory, cap_bytes=2000).reap(keep={"oldest"})
    assert [p.name for p in removed] == ["middle.bin"]
    assert (directory / "oldest.bin").exists()


def test_reaper_keeps_evicting_until_it_fits(tmp_path):
    directory = make_snapshots(tmp_path / "kv-slots", {f"s{i}": 1000 for i in range(6)})
    removed = SnapshotReaper(directory, cap_bytes=2500).reap()
    assert len(removed) == 4 and len(list(directory.glob("*.bin"))) == 2


def test_touch_and_drop(tmp_path):
    directory = make_snapshots(tmp_path / "kv-slots", {"a": 10})
    reaper = SnapshotReaper(directory)
    assert reaper.has("a") and not reaper.has("b")
    reaper.touch("a")
    assert reaper.drop("a") is True and reaper.drop("a") is False


def test_missing_directory_is_not_an_error(tmp_path):
    reaper = SnapshotReaper(tmp_path / "never-created")
    assert reaper.reap() == [] and reaper.total_bytes() == 0


def test_default_cap_matches_the_tdd():
    assert SNAPSHOT_DIR_CAP_BYTES == 4 * 1024**3

"""Staging tests. The behaviours worth locking down are the refusals: a bad source drive
must be caught *before* a four-minute copy, and corruption introduced *by* the copy must be
caught after it — those are two different failures with two different remedies (TDD §10.3).
"""

from __future__ import annotations

import pytest

from bundle.layout import PRIVATE_DIRS
from bundle.manifest import IntegrityError, Manifest
from bundle.stage import free_bytes, stage, warm_page_cache
from bundle.tests.test_manifest import make_bundle


@pytest.fixture
def usb(tmp_path):
    root = make_bundle(tmp_path / "usb")
    Manifest.build(root).write(root / "models" / "MANIFEST.json")
    (root / "gw").mkdir()
    (root / "gw" / "app.py").write_text("# gateway\n")
    (root / "versions.lock").write_text("LLAMA_CPP_REF=b10035\n")
    return root


def test_stage_copies_and_reverifies(usb, tmp_path):
    dst = tmp_path / "opt-tutor"
    report = stage(usb, dst, warm=False)

    assert report.artifacts == 3
    assert report.steps == ["verify:source", "copy", "verify:destination"]
    assert (dst / "models" / "core" / "core.gguf").read_bytes() == (
        usb / "models" / "core" / "core.gguf"
    ).read_bytes()
    # Non-manifest bundle content (the gateway app, the lock) rides along.
    assert (dst / "gw" / "app.py").exists()
    assert (dst / "versions.lock").exists()


def test_private_dirs_are_0700(usb, tmp_path):
    dst = tmp_path / "opt-tutor"
    stage(usb, dst, warm=False)
    for rel in PRIVATE_DIRS:
        assert (dst / rel).stat().st_mode & 0o777 == 0o700, rel


def test_corrupt_source_is_refused_before_any_copy(usb, tmp_path):
    (usb / "models" / "core" / "core.gguf").write_bytes(b"GGUF" + b"\xff" * 4096)
    dst = tmp_path / "opt-tutor"
    with pytest.raises(IntegrityError, match="core.gguf"):
        stage(usb, dst, warm=False)
    assert not (dst / "models").exists(), "nothing may be copied from a drive that failed verify"


def test_corruption_during_copy_is_caught_by_the_second_verify(usb, tmp_path, monkeypatch):
    """The two verifications are not redundant: this one only fails on the second pass."""
    import bundle.stage as stage_mod

    real_copy = stage_mod.shutil.copy2

    def flaky_copy(src, dst_, *a, **kw):
        real_copy(src, dst_, *a, **kw)
        if str(dst_).endswith("core.gguf"):  # simulate a bad write on cheap flash
            data = bytearray(open(dst_, "rb").read())
            data[100] ^= 0x08
            open(dst_, "wb").write(bytes(data))

    monkeypatch.setattr(stage_mod.shutil, "copy2", flaky_copy)
    with pytest.raises(IntegrityError) as e:
        stage(usb, tmp_path / "opt-tutor", warm=False)
    assert "core.gguf" in str(e.value)
    assert "sha256" in str(e.value)


def test_refuses_when_the_disk_cannot_hold_the_bundle(usb, tmp_path, monkeypatch):
    monkeypatch.setattr("bundle.stage.free_bytes", lambda _p: 1024)
    with pytest.raises(RuntimeError, match="not enough free space"):
        stage(usb, tmp_path / "opt-tutor", warm=False)


def test_free_bytes_walks_up_to_an_existing_parent(tmp_path):
    assert free_bytes(tmp_path / "does" / "not" / "exist" / "yet") > 0


def test_warm_falls_back_to_reading_when_vmtouch_is_absent(usb, monkeypatch):
    monkeypatch.setattr("bundle.stage.shutil.which", lambda _n: None)
    assert warm_page_cache(usb / "models" / "core") is True
    assert warm_page_cache(usb / "models" / "nope") is False


def test_report_reads_like_something_an_operator_can_act_on(usb, tmp_path):
    ticks = iter([0.0, 4.0])
    report = stage(usb, tmp_path / "opt", warm=False, clock=lambda: next(ticks))
    text = str(report)
    assert "3 artifacts" in text and "MiB/s" in text

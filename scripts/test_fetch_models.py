"""Offline tests for the model fetcher and verifier (TDD T2).

No network. The parts worth testing here are the ones where a silent bug is expensive:
the size flag (a wrong quant looks identical to a right one except for its size), the
licence gate (ships to third parties), the manifest merge (a partial run must not erase
the record of everything else), and the hash check that backs the "verify twice" claim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_models as fm  # noqa: E402
import model_specs as ms  # noqa: E402
import verify_models as vm  # noqa: E402

# --------------------------------------------------------------------------------------
# size verdicts — "usually the wrong quant"
# --------------------------------------------------------------------------------------


def _art(**kw):
    base = dict(
        name="x",
        role="r",
        tier="resident",
        repo="o/r",
        dest="models/x",
        license=ms.LicenseSource(spdx="MIT"),
        planning_bytes=100 * ms.MiB,
        file="x.gguf",
    )
    base.update(kw)
    return ms.Artifact(**base)


@pytest.mark.parametrize(
    "actual,expected",
    [
        (100 * ms.MiB, "ok"),  # exact
        (119 * ms.MiB, "ok"),  # +19%, inside tolerance
        (81 * ms.MiB, "ok"),  # -19%, inside tolerance
        (121 * ms.MiB, "FLAG"),  # +21%
        (79 * ms.MiB, "FLAG"),  # -21%
    ],
)
def test_size_verdict_approx(actual, expected):
    assert fm.size_verdict(_art(), actual)[0] == expected


@pytest.mark.parametrize(
    "actual,expected",
    [(50 * ms.MiB, "ok"), (100 * ms.MiB, "ok"), (101 * ms.MiB, "FLAG")],
)
def test_size_verdict_max_is_a_ceiling_not_a_target(actual, expected):
    """A "< 100 MiB" budget must not flag a pleasantly small file."""
    assert fm.size_verdict(_art(size_mode="max"), actual)[0] == expected


# --------------------------------------------------------------------------------------
# licence policy — a ship blocker, not a warning
# --------------------------------------------------------------------------------------


def test_non_permissive_licence_is_refused():
    art = _art(license=ms.LicenseSource(spdx="CC-BY-NC-SA-4.0", note="non-commercial"))
    with pytest.raises(fm.Stop) as exc:
        fm.capture_license(None, art, "deadbeef", dry_run=True)
    assert "not on the permissive allow-list" in str(exc.value)


def test_every_shipped_artifact_declares_a_permissive_licence():
    for art in ms.ARTIFACTS + ms.QUANT_VARIANTS:
        assert art.license.spdx in ms.ALLOWED_LICENSES, art.name


def test_the_rejected_piper_voice_is_not_the_pinned_one():
    """lessac is the obvious default and is NOT redistributable — guard the regression."""
    tts = ms.BY_NAME["tts"]
    assert "lessac" not in tts.repo
    assert any("lessac" in r for r in tts.rejected), "the trap must stay documented"


def test_mmproj_q8_gap_is_recorded_rather_than_papered_over():
    assert "mmproj-q8_0" in ms.UNRESOLVED
    assert ms.BY_NAME["mmproj"].file == "mmproj-F16.gguf"


# --------------------------------------------------------------------------------------
# manifest merge — a partial run must not erase the rest
# --------------------------------------------------------------------------------------


def test_merge_keeps_artifacts_absent_from_this_run():
    existing = [{"name": "core", "bytes": 1}, {"name": "embed", "bytes": 2}]
    fresh = [{"name": "tts", "bytes": 3}]
    names = [e["name"] for e in fm.merge_manifest(existing, fresh)]
    assert set(names) == {"core", "embed", "tts"}


def test_merge_lets_this_run_win():
    merged = fm.merge_manifest([{"name": "core", "bytes": 1}], [{"name": "core", "bytes": 9}])
    assert merged == [{"name": "core", "bytes": 9}]


def test_merge_output_is_in_canonical_spec_order():
    fresh = [{"name": "embed"}, {"name": "core"}, {"name": "asr"}]
    assert [e["name"] for e in fm.merge_manifest([], fresh)] == ["core", "asr", "embed"]


# --------------------------------------------------------------------------------------
# the hash check behind "verify twice"
# --------------------------------------------------------------------------------------


def _manifest_with(tmp_path: Path, payload: bytes):
    f = tmp_path / "artifact.bin"
    f.write_bytes(payload)
    return f, {
        "generated_at": "now",
        "artifacts": [
            {
                "name": "core",
                "tier": "resident",
                "license": "MIT",
                "fetched": True,
                "path": str(f),
                "bytes": len(payload),
                "sha256": fm.sha256_file(f),
            }
        ],
    }


def test_hash_check_passes_on_intact_file(tmp_path, monkeypatch):
    _, manifest = _manifest_with(tmp_path, b"hello world" * 100)
    monkeypatch.setattr(vm, "REPO_ROOT", Path("/"))
    vm.results.clear()
    vm.check_hashes(manifest)
    assert [r[1] for r in vm.results] == [vm.PASS]


def test_hash_check_catches_a_single_flipped_bit(tmp_path, monkeypatch):
    """The bitrot case TDD §10.2 exists for: same length, one byte different."""
    f, manifest = _manifest_with(tmp_path, b"hello world" * 100)
    data = bytearray(f.read_bytes())
    data[5] ^= 0x01
    f.write_bytes(bytes(data))

    monkeypatch.setattr(vm, "REPO_ROOT", Path("/"))
    vm.results.clear()
    vm.check_hashes(manifest)
    assert [r[1] for r in vm.results] == [vm.FAIL]
    assert str(f) in vm.results[0][2], "the failure must name the file"


def test_hash_check_catches_a_missing_file(tmp_path, monkeypatch):
    f, manifest = _manifest_with(tmp_path, b"x" * 64)
    f.unlink()
    monkeypatch.setattr(vm, "REPO_ROOT", Path("/"))
    vm.results.clear()
    vm.check_hashes(manifest)
    assert vm.results[0][1] == vm.FAIL
    assert "MISSING" in vm.results[0][2]


# --------------------------------------------------------------------------------------
# budget + directory digest
# --------------------------------------------------------------------------------------


def test_resident_budget_fails_when_over_cap():
    manifest = {
        "artifacts": [
            {
                "name": "core",
                "tier": "resident",
                "fetched": True,
                "bytes": fm.RESIDENT_CAP_BYTES + 1,
            }
        ]
    }
    vm.results.clear()
    vm.check_resident_budget(manifest)
    assert vm.results[0][1] == vm.FAIL
    assert "OVER by" in vm.results[0][2]


def test_on_demand_artifacts_do_not_count_against_the_resident_cap():
    manifest = {
        "artifacts": [{"name": "draft", "tier": "on-demand", "fetched": True, "bytes": 8 * ms.GiB}]
    }
    vm.results.clear()
    vm.check_resident_budget(manifest)
    assert vm.results[0][1] == vm.PASS


def test_strict_distinguishes_missing_tooling_from_deliberate_skips():
    """--strict must fail on an unverifiable check, never on tier B we chose not to fetch."""
    vm.results.clear()
    vm.record("smoke/asr", vm.SKIP, "asr not fetched", expected=True)
    blocked = [r for r in vm.results if r[1] == vm.SKIP and not r[3]]
    assert blocked == [], "a deliberate skip must not block --strict"

    vm.record("load/core", vm.SKIP, "llama-cli not found")
    blocked = [r for r in vm.results if r[1] == vm.SKIP and not r[3]]
    assert [r[0] for r in blocked] == ["load/core"]


def test_dir_digest_is_order_independent_but_content_sensitive():
    a = fm.FetchedFile("a", "p/a", 1, "aa")
    b = fm.FetchedFile("b", "p/b", 1, "bb")
    assert fm._dir_digest([a, b]) == fm._dir_digest([b, a])
    c = fm.FetchedFile("b", "p/b", 1, "cc")
    assert fm._dir_digest([a, b]) != fm._dir_digest([a, c])


def test_gated_artifacts_need_their_flag():
    class Args:
        with_multilingual_asr = False
        with_kokoro = False
        with_draft = False
        quant_variants = False

    assert fm.will_fetch(ms.BY_NAME["core"], Args()) is True
    assert fm.will_fetch(ms.BY_NAME["draft"], Args()) is False
    Args.with_draft = True
    assert fm.will_fetch(ms.BY_NAME["draft"], Args()) is True


def test_unfetched_artifacts_report_zero_bytes_on_disk():
    """`bytes` means bytes on disk. An unfetched directory once reported its full size,
    which made a tier B artifact look like it was occupying the resident budget."""
    path = fm.MANIFEST_PATH
    if not path.exists():
        pytest.skip("no manifest fetched in this workspace")
    for a in json.loads(path.read_text())["artifacts"]:
        if not a["fetched"]:
            assert a["bytes"] == 0, f"{a['name']} is not fetched but claims disk bytes"
            assert a["sha256"] == "", f"{a['name']} is not fetched but carries a hash"


def test_manifest_on_disk_matches_the_documented_shape():
    """The real manifest, if present, must carry every field downstream consumers read."""
    path = fm.MANIFEST_PATH
    if not path.exists():
        pytest.skip("no manifest fetched in this workspace")
    doc = json.loads(path.read_text())
    assert doc["generated_at"]
    required = {
        "name",
        "role",
        "repo",
        "revision",
        "file",
        "path",
        "bytes",
        "sha256",
        "license",
        "license_url",
        "tier",
        "fetched",
    }
    for a in doc["artifacts"]:
        assert required <= set(a), f"{a['name']} missing {required - set(a)}"
        if a["fetched"]:
            assert a["revision"] and len(a["revision"]) >= 7, a["name"]

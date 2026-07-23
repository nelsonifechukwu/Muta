"""The integrity gate is only worth having if it fires. These tests corrupt things on
purpose — one byte, one truncation, one missing file — and assert the failure *names the
file* (TDD §10.2: "any mismatch → refuse to start, name the file")."""

from __future__ import annotations

import json

import pytest

from bundle.manifest import (
    ALLOWED_LICENSES,
    IntegrityError,
    Manifest,
    main,
    sha256_file,
    verify_or_raise,
)


def make_bundle(root, *, gguf=b"GGUF" + b"\x00" * 4096, extra=True):
    (root / "models" / "core").mkdir(parents=True)
    (root / "bin").mkdir()
    (root / "models" / "core" / "core.gguf").write_bytes(gguf)
    (root / "bin" / "llama-server").write_bytes(b"\x7fELF" + b"binary")
    if extra:
        (root / "index").mkdir()
        (root / "index" / "faiss.bin").write_bytes(b"index")
    return root


@pytest.fixture
def bundle(tmp_path):
    return make_bundle(tmp_path / "dist")


def test_build_hashes_every_artifact_under_the_manifest_roots(bundle):
    m = Manifest.build(bundle)
    paths = {a.path for a in m.artifacts}
    assert paths == {"models/core/core.gguf", "bin/llama-server", "index/faiss.bin"}
    assert m.total_bytes == sum((bundle / p).stat().st_size for p in paths)


def test_build_records_the_real_sha256(bundle):
    m = Manifest.build(bundle)
    gguf = next(a for a in m.artifacts if a.path.endswith("core.gguf"))
    assert gguf.sha256 == sha256_file(bundle / "models/core/core.gguf")


def test_licenses_apply_by_prefix_and_exact_path(bundle):
    m = Manifest.build(bundle, licenses={"models": "Apache-2.0", "bin/llama-server": "MIT"})
    by_path = {a.path: a.license for a in m.artifacts}
    assert by_path["models/core/core.gguf"] == "Apache-2.0"
    assert by_path["bin/llama-server"] == "MIT"


def test_build_refuses_a_non_redistributable_license(bundle):
    with pytest.raises(ValueError, match="not redistributable"):
        Manifest.build(bundle, licenses={"models": "CC-BY-NC-4.0"})
    assert "CC-BY-NC-4.0" not in ALLOWED_LICENSES


def test_roundtrip_through_json_is_lossless(bundle, tmp_path):
    m = Manifest.build(bundle, licenses={"models": "Apache-2.0"})
    path = m.write(tmp_path / "MANIFEST.json")
    assert Manifest.from_json(path.read_text()) == m


def test_manifest_json_is_sorted_so_diffs_are_reviewable(bundle):
    payload = json.loads(Manifest.build(bundle).to_json())
    paths = [a["path"] for a in payload["artifacts"]]
    assert paths == sorted(paths)


def test_verify_is_clean_on_an_untouched_bundle(bundle):
    m = Manifest.build(bundle)
    m.write(bundle / "models" / "MANIFEST.json")
    assert m.verify(bundle) == []
    assert verify_or_raise(bundle).artifacts == m.artifacts


def test_one_flipped_byte_is_caught_and_the_file_is_named(bundle):
    m = Manifest.build(bundle)
    m.write(bundle / "models" / "MANIFEST.json")

    target = bundle / "models" / "core" / "core.gguf"
    data = bytearray(target.read_bytes())
    data[2048] ^= 0x01  # single-bit flip in the middle: the classic cheap-flash failure
    target.write_bytes(bytes(data))

    with pytest.raises(IntegrityError) as e:
        verify_or_raise(bundle)
    assert "models/core/core.gguf" in str(e.value)
    assert "sha256" in str(e.value)


def test_truncation_is_reported_as_size_not_hash(bundle):
    """A short read is conclusive without hashing 2.5 GiB — and the operator's next move
    differs (bad copy vs bad drive), so the reason has to be specific."""
    m = Manifest.build(bundle)
    (bundle / "models" / "core" / "core.gguf").write_bytes(b"GGUF")
    (bad,) = [x for x in m.verify(bundle) if x.path.endswith("core.gguf")]
    assert bad.reason == "size"


def test_missing_file_is_named(bundle):
    m = Manifest.build(bundle)
    (bundle / "bin" / "llama-server").unlink()
    bad = m.verify(bundle)
    assert [x.path for x in bad] == ["bin/llama-server"]
    assert bad[0].reason == "missing"


def test_shallow_verify_skips_hashing_but_still_catches_size(bundle):
    m = Manifest.build(bundle)
    data = bytearray((bundle / "index" / "faiss.bin").read_bytes())
    data[0] ^= 0xFF
    (bundle / "index" / "faiss.bin").write_bytes(bytes(data))  # same size, different content
    assert m.verify(bundle, deep=False) == []
    assert [x.reason for x in m.verify(bundle, deep=True)] == ["sha256"]


def test_missing_manifest_is_itself_an_integrity_failure(bundle):
    with pytest.raises(IntegrityError, match="MANIFEST.json"):
        verify_or_raise(bundle)


def test_cli_build_then_verify(bundle, capsys):
    assert main(["build", "--root", str(bundle)]) == 0
    assert main(["verify", "--root", str(bundle)]) == 0
    assert "3 artifacts verified" in capsys.readouterr().out


def test_cli_verify_exits_nonzero_and_names_the_file(bundle, capsys):
    main(["build", "--root", str(bundle)])
    (bundle / "bin" / "llama-server").write_bytes(b"tampered")
    assert main(["verify", "--root", str(bundle)]) == 1
    assert "bin/llama-server" in capsys.readouterr().err

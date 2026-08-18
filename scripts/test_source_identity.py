from __future__ import annotations

from scripts import source_identity


def test_source_identity_is_stable_and_self_describing():
    first = source_identity.source_identity()
    second = source_identity.source_identity()
    assert first == second
    assert first["identifier"].endswith(first["source_tree_sha256"][:12])
    assert first["source_file_count"] > 100

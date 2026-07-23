"""GGUF header-reader tests (TDD T5).

Most cases are built from synthetic headers so the edge shapes (per-layer KV-head arrays,
missing key_length, truncation) are covered without shipping fixtures; the real dev model is
also read when present, because a parser that only satisfies its own fixtures proves nothing.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from runtime.gguf import GGUFError, read_metadata

FIXTURE = Path("models/Qwen3-0.6B/Qwen3-0.6B-Q4_K_M.gguf")

# GGUF value type ids used below
U32, U64, STR, ARR = 4, 10, 8, 9


def _kv(key: str, type_id: int, payload: bytes) -> bytes:
    k = key.encode()
    return struct.pack("<Q", len(k)) + k + struct.pack("<I", type_id) + payload


def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _str(v: str) -> bytes:
    b = v.encode()
    return struct.pack("<Q", len(b)) + b


def _arr_u32(values: list[int]) -> bytes:
    return _u32(U32) + struct.pack("<Q", len(values)) + b"".join(_u32(v) for v in values)


def write_gguf(path: Path, entries: list[bytes], *, version: int = 3, tensors: int = 0) -> Path:
    body = b"".join(entries)
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", version, tensors, len(entries)) + body)
    return path


def qwen_like(path: Path, *, layers=36, kv_heads=8, heads=32, key_len=128, value_len=None) -> Path:
    entries = [
        _kv("general.architecture", STR, _str("qwen3")),
        _kv("qwen3.block_count", U32, _u32(layers)),
        _kv("qwen3.attention.head_count", U32, _u32(heads)),
        _kv("qwen3.attention.head_count_kv", U32, _u32(kv_heads)),
        _kv("qwen3.attention.key_length", U32, _u32(key_len)),
        _kv("qwen3.context_length", U32, _u32(32768)),
        _kv("qwen3.embedding_length", U32, _u32(heads * key_len)),
    ]
    if value_len is not None:
        entries.append(_kv("qwen3.attention.value_length", U32, _u32(value_len)))
    return write_gguf(path, entries)


def test_reads_the_five_numbers_the_kv_budget_needs(tmp_path):
    md = read_metadata(qwen_like(tmp_path / "m.gguf"))
    assert md.architecture == "qwen3"
    assert (md.n_layer, md.n_kv_head, md.n_head, md.head_dim_k) == (36, 8, 32, 128)
    assert md.head_dim_v == md.head_dim_k  # falls back to K when value_length is absent
    assert md.trained_context == 32768


def test_head_dim_falls_back_to_embedding_over_heads(tmp_path):
    entries = [
        _kv("general.architecture", STR, _str("llama")),
        _kv("llama.block_count", U32, _u32(32)),
        _kv("llama.attention.head_count", U32, _u32(32)),
        _kv("llama.attention.head_count_kv", U32, _u32(8)),
        _kv("llama.embedding_length", U32, _u32(4096)),
    ]
    md = read_metadata(write_gguf(tmp_path / "l.gguf", entries))
    assert md.head_dim_k == 128


def test_per_layer_kv_head_arrays_take_the_max_not_the_mean(tmp_path):
    """Hybrid attention publishes one KV-head count per layer. Averaging under-reports the
    full-attention layers, and under-budgeting KV is an OOM kill — a disqualification, not a
    slow score. Over-budgeting only costs a slot."""
    entries = [
        _kv("general.architecture", STR, _str("hybrid")),
        _kv("hybrid.block_count", U32, _u32(4)),
        _kv("hybrid.attention.head_count", U32, _u32(16)),
        _kv("hybrid.attention.head_count_kv", ARR, _arr_u32([8, 0, 8, 0])),
        _kv("hybrid.attention.key_length", U32, _u32(128)),
    ]
    md = read_metadata(write_gguf(tmp_path / "h.gguf", entries))
    assert md.n_kv_head == 8


def test_separate_key_and_value_lengths_are_kept_apart(tmp_path):
    md = read_metadata(qwen_like(tmp_path / "m.gguf", key_len=192, value_len=128))
    assert (md.head_dim_k, md.head_dim_v) == (192, 128)


def test_huge_token_arrays_are_summarised_not_materialised(tmp_path):
    """A vocab array is ~150k strings and nothing here needs it; holding it would make a
    header read cost more RAM than the budget it exists to compute."""
    entries = [
        _kv("general.architecture", STR, _str("qwen3")),
        _kv("qwen3.block_count", U32, _u32(1)),
        _kv("tokenizer.ggml.tokens", ARR, _u32(U32) + struct.pack("<Q", 2000) + b"".join(_u32(i) for i in range(2000))),
    ]
    md = read_metadata(write_gguf(tmp_path / "v.gguf", entries))
    assert md.kv["tokenizer.ggml.tokens"] == "<array len=2000>"


def test_non_gguf_file_is_rejected_by_magic(tmp_path):
    p = tmp_path / "not.gguf"
    p.write_bytes(b"NOPE" + b"\x00" * 32)
    with pytest.raises(GGUFError, match="bad magic"):
        read_metadata(p)


def test_truncated_header_is_rejected(tmp_path):
    p = tmp_path / "short.gguf"
    p.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 5))  # claims 5 kv pairs, has none
    with pytest.raises(GGUFError, match="truncated"):
        read_metadata(p)


def test_unsupported_version_is_rejected(tmp_path):
    with pytest.raises(GGUFError, match="unsupported GGUF version"):
        read_metadata(qwen_like(tmp_path / "m.gguf") and write_gguf(tmp_path / "v1.gguf", [], version=1))


@pytest.mark.skipif(not FIXTURE.exists(), reason="dev fixture GGUF not provisioned")
def test_reads_the_real_dev_model():
    md = read_metadata(FIXTURE)
    assert md.architecture == "qwen3"
    assert md.n_layer == 28 and md.n_kv_head == 8 and md.head_dim_k == 128
    assert md.file_bytes == 396_705_472  # the byte count pinned in versions.lock

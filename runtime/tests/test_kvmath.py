"""KV budget tests (TDD §5.2, T5).

The first test is the important one: it reproduces the TDD's own worked example to the
quoted KiB. If this module and the TDD ever disagree, one of them is wrong about how much
RAM a slot costs — and that number decides how many students the classroom demo serves.
"""

from __future__ import annotations

import pytest

from runtime.gguf import read_metadata
from runtime.kvmath import (
    CACHE_TYPE_BYTES,
    CORE_TEXT_CAP_MIB,
    KVCost,
    budget,
    budget_table,
    cache_type_bytes,
    main,
    render_markdown,
)
from runtime.profiles import PROFILES
from runtime.tests.test_gguf import qwen_like


def tdd_example(cache_type: str = "q8_0") -> KVCost:
    """n_layer=36, n_kv_head=8, head_dim=128 — the representative Qwen-family values in §5.2."""
    return KVCost(36, 8, 128, 128, cache_type, cache_type)


def test_reproduces_the_tdd_worked_example():
    cost = tdd_example("f16")
    assert cost.elements_per_token == 73_728  # 2 × 36 × 8 × 128
    assert cost.kib_per_token == pytest.approx(144.0, abs=0.1)
    assert cost.mib_for(4096) == pytest.approx(576, abs=1)


def test_q8_0_and_q5_1_rows_of_the_worked_example():
    assert tdd_example("q8_0").kib_per_token == pytest.approx(76.5, abs=0.1)
    assert tdd_example("q8_0").mib_for(4096) == pytest.approx(306, abs=1)
    assert tdd_example("q5_1").kib_per_token == pytest.approx(54.0, abs=0.1)
    assert tdd_example("q5_1").mib_for(4096) == pytest.approx(216, abs=1)


def test_block_quant_sizes_are_exact_not_rounded_bit_counts():
    """q8_0 is 34 bytes per 32 elements, not 32: the block header is 6% of the cache, which
    is a whole slot at classroom scale."""
    assert CACHE_TYPE_BYTES["q8_0"] == 34 / 32
    assert CACHE_TYPE_BYTES["q5_1"] == 24 / 32
    assert CACHE_TYPE_BYTES["q4_0"] == 18 / 32


def test_unknown_cache_type_names_the_alternatives_and_the_tq3_0_trap():
    with pytest.raises(KeyError, match="tq3_0"):
        cache_type_bytes("tq3_0")  # appears in the D6 ladder; not a mainline KV type


def test_asymmetric_head_dims_are_not_doubled_blindly():
    """The `2 ×` in the TDD formula IS the K + V sum; with different head dims it stops
    being a factor of two."""
    cost = KVCost(36, 8, 192, 128, "f16", "f16")
    assert cost.elements_per_token == 36 * 8 * (192 + 128)


def test_mixed_k_and_v_quantization():
    mixed = KVCost(36, 8, 128, 128, "q8_0", "q5_1")
    assert mixed.bytes_per_token < tdd_example("q8_0").bytes_per_token
    assert mixed.bytes_per_token > tdd_example("q5_1").bytes_per_token


# --- budget rows -------------------------------------------------------------------------


def test_classroom_8_at_4b_scale_blows_the_cap_exactly_as_the_tdd_warns():
    """§5.2: 2.5 weights + 2.4 KV + 0.6 buffers ≈ 5.5 GiB against a 4300 MiB cap."""
    cost = tdd_example("q8_0")
    row = budget(cost, PROFILES["classroom-8"], weights_mib=2560)
    assert not row.fits
    assert row.kv_mib == pytest.approx(2448, abs=10)


def test_classroom_6_short_is_the_row_that_fits():
    cost = tdd_example("q8_0")
    row = budget(cost, PROFILES["classroom"], weights_mib=2560)
    assert row.fits
    assert row.total_mib == pytest.approx(4078, abs=20)  # ≈ 4.0 GiB, the TDD's ✓ row
    assert row.cap_mib == CORE_TEXT_CAP_MIB


def test_cheaper_kv_buys_back_context():
    """The D6 ladder is a context lever: classroom-6 (4096 ctx/slot) does not fit at q8_0 —
    §5.2 calls that row "still tight" and lands on 4.9 GiB, which this reproduces — but the
    same row fits at q4_0. Note q5_1 is NOT enough, so the ladder is not a free win."""
    weights = 2560
    rows = {q: budget(tdd_example(q), PROFILES["classroom-6"], weights_mib=weights) for q in ("q8_0", "q5_1", "q4_0")}
    assert rows["q8_0"].total_mib == pytest.approx(4996, abs=20)  # ≈ 4.9 GiB, as the TDD says
    assert not rows["q8_0"].fits
    assert not rows["q5_1"].fits
    assert rows["q4_0"].fits
    assert rows["q8_0"].kv_mib > rows["q5_1"].kv_mib > rows["q4_0"].kv_mib


def test_lower_ubatch_shrinks_the_compute_buffer():
    from dataclasses import replace

    small = replace(PROFILES["classroom"], ubatch=256)
    big = PROFILES["classroom"]
    cost = tdd_example()
    assert budget(cost, small, weights_mib=2560).buffers_mib < budget(cost, big, weights_mib=2560).buffers_mib


def test_measured_buffer_size_overrides_the_planning_value():
    row = budget(tdd_example(), PROFILES["classroom"], weights_mib=2560, buffers_mib=410)
    assert row.buffers_mib == 410


# --- from a real file --------------------------------------------------------------------


def test_table_is_derived_from_the_gguf_not_from_constants(tmp_path):
    md = read_metadata(qwen_like(tmp_path / "m.gguf", layers=36, kv_heads=8, key_len=128))
    cost, rows = budget_table(md)
    assert cost.n_layer == 36 and cost.n_kv_head == 8
    assert {r.profile.name for r in rows} == set(PROFILES)
    assert all(r.weights_mib == md.file_bytes / 1024**2 for r in rows)


def test_metadata_without_the_kv_numbers_refuses_to_guess(tmp_path):
    from runtime.tests.test_gguf import STR, _kv, _str, write_gguf

    md = read_metadata(write_gguf(tmp_path / "bare.gguf", [_kv("general.architecture", STR, _str("mystery"))]))
    with pytest.raises(ValueError, match="cannot derive the KV budget"):
        budget_table(md)


def test_markdown_marks_the_unmeasured_number_as_provisional(tmp_path):
    md = read_metadata(qwen_like(tmp_path / "m.gguf"))
    cost, rows = budget_table(md)
    doc = render_markdown(md, cost, rows)
    assert "PROVISIONAL" in doc and "[MEASURE:" in doc
    assert "| classroom |" in doc and "elements/token" in doc


def test_cli_writes_the_table(tmp_path, capsys):
    model = qwen_like(tmp_path / "m.gguf")
    out = tmp_path / "kv-budget.md"
    assert main([str(model), "--markdown", str(out)]) == 0
    assert "KV budget" in out.read_text()


def test_cli_fails_when_nothing_fits(tmp_path, capsys):
    model = qwen_like(tmp_path / "m.gguf")
    assert main([str(model), "--cache-type", "f32", "--cap-mib", "10"]) == 1
    assert "no profile fits" in capsys.readouterr().err

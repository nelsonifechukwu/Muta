from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layer_selection = _load("layer_selection")


def test_block_influence_is_zero_for_identity_and_one_for_orthogonal():
    x = np.array([[1.0, 0.0], [0.0, 2.0]])
    assert layer_selection.block_influence(x, x) == pytest.approx(0.0, abs=1e-6)
    y = np.array([[0.0, 1.0], [3.0, 0.0]])
    assert layer_selection.block_influence(x, y) == pytest.approx(1.0)


def test_angular_distance_is_zero_same_half_orthogonal_one_opposite():
    x = np.array([[1.0, 0.0]])
    assert layer_selection.angular_distance(x, x) == pytest.approx(0.0, abs=1e-6)
    assert layer_selection.angular_distance(x, np.array([[0.0, 1.0]])) == pytest.approx(0.5)
    assert layer_selection.angular_distance(x, -x) == pytest.approx(1.0)


def test_select_contiguous_picks_minimum_inside_protections():
    # 8 layers, blocks of 3: start 0 has the smallest distance but is protected.
    dist = {0: 0.01, 1: 0.30, 2: 0.05, 3: 0.20, 4: 0.09, 5: 0.40}
    assert layer_selection.select_contiguous(dist, 3, 8, 2, 1) == [2, 3, 4]
    # protect_last=1 forbids a block that would include layer 7 (start 5 → 5,6,7).
    dist_tail = {5: 0.0, 2: 0.5, 3: 0.6, 4: 0.7}
    assert layer_selection.select_contiguous(dist_tail, 3, 8, 2, 1) == [2, 3, 4]


def test_select_contiguous_raises_when_nothing_is_eligible():
    with pytest.raises(ValueError):
        layer_selection.select_contiguous({0: 0.1}, 3, 8, 2, 1)


def test_select_lowest_bi_respects_protections_and_sorts_ascending():
    bi = [0.0, 0.0, 0.9, 0.1, 0.5, 0.2, 0.05, 0.0]  # layer 7 lowest but protected
    assert layer_selection.select_lowest_bi(bi, 3, 2, 1) == [3, 5, 6]


def test_renumber_plan_and_kept_indices_preserve_order():
    assert layer_selection.kept_layer_indices(4, [1, 2]) == [0, 3]
    assert layer_selection.renumber_plan(4, [1, 2]) == {0: 0, 3: 1}


calibration = _load("calibration")


def test_render_text_uses_lm_eval_boundary_for_raw_and_chatml_for_chat():
    raw = {"mode": "raw", "prompt": "Q: 2+2?\nAnswer:", "completion": "4", "source": "arc"}
    assert calibration.render_text(raw) == "Q: 2+2?\nAnswer: 4"
    chat = {"mode": "chat", "prompt": "hi", "completion": "hello", "source": "gsm8k"}
    assert calibration.render_text(chat) == (
        "<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\nhello<|im_end|>"
    )


def test_stratified_sample_is_deterministic_and_balanced():
    rows = [{"source": s, "text": f"{s}{i}"} for s in ("a", "b") for i in range(10)]
    first = calibration.stratified_sample(rows, per_source=3, seed=3407)
    second = calibration.stratified_sample(rows, per_source=3, seed=3407)
    assert first == second
    assert sorted(r["source"] for r in first) == ["a", "a", "a", "b", "b", "b"]


def test_contaminated_detects_exact_and_high_ngram_overlap_only():
    banned = ["A trader in Onitsha buys 40 kg of rice at ₦1,850 per kg."]
    assert calibration.contaminated("x " + banned[0] + " y", banned)
    # Not an exact substring (first word differs) but 6 of the phrase's 7 eight-grams survive.
    near = "One trader in Onitsha buys 40 kg of rice at ₦1,850 per kg."
    assert calibration.contaminated(near, banned)
    assert not calibration.contaminated("A farmer sells 3 goats for 40,000 naira.", banned)

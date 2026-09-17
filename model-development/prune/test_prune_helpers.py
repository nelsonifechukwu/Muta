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


block_influence = _load("block_influence")


def test_accumulate_and_finalize_rank_the_identity_layer_lowest():
    # 4 layers on 3 tokens of hidden size 2. Layer 1 is the identity (BI 0);
    # layers 0, 2 rotate by 90°; layer 3 rotates by 45°.
    t = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    rot90 = np.array([[0.0, -1.0], [1.0, 0.0]])
    rot45 = np.array([[np.cos(np.pi / 4), -np.sin(np.pi / 4)], [np.sin(np.pi / 4), np.cos(np.pi / 4)]])
    x0 = t
    x1 = x0 @ rot90.T
    x2 = x1
    x3 = x2 @ rot90.T
    x4 = x3 @ rot45.T
    stats = block_influence.new_stats(n_layers=4, blocks=[2])
    block_influence.accumulate(stats, [x0, x1, x2, x3], [x1, x2, x3, x4], blocks=[2])
    result = block_influence.finalize(stats, blocks=[2], protect_first=0, protect_last=0)
    assert result["bi"][1] == pytest.approx(0.0, abs=1e-6)
    assert result["bi"][0] == pytest.approx(1.0)
    assert result["bi"][3] == pytest.approx(1 - np.cos(np.pi / 4))
    # 2-blocks: start 1 = layers 1,2 → x1→x3 is 90° (0.5); start 0 → x0→x2 is 90° (0.5);
    # start 2 → x2→x4 is 135° (0.75). Ties resolve to the lowest start.
    assert result["block_distance"]["2"]["2"] == pytest.approx(0.75)
    assert result["selections"]["contiguous"]["2"] == [0, 1]
    assert result["selections"]["lowest_bi"]["2"] == [1, 3]


prune_gguf_layers = _load("prune_gguf_layers")  # imports gguf lazily, so loading is safe


def test_plan_tensor_names_renumbers_blocks_and_keeps_globals():
    names = ["token_embd.weight", "blk.0.attn_q.weight", "blk.1.attn_q.weight",
             "blk.2.attn_q.weight", "blk.3.attn_q.weight", "output_norm.weight"]
    plan = prune_gguf_layers.plan_tensor_names(names, 4, [1, 2])
    assert plan == [
        ("token_embd.weight", "token_embd.weight"),
        ("blk.0.attn_q.weight", "blk.0.attn_q.weight"),
        ("blk.3.attn_q.weight", "blk.1.attn_q.weight"),
        ("output_norm.weight", "output_norm.weight"),
    ]


def test_params_from_shapes_multiplies_dims():
    assert prune_gguf_layers.params_from_shapes([(8, 4), (4,), (2, 3, 5)]) == 32 + 4 + 30


def test_prune_gguf_roundtrip_drops_layers_and_rewrites_block_count(tmp_path):
    pytest.importorskip("gguf")  # inside the test: a missing dep must not skip the whole module
    from gguf import GGUFReader, GGUFWriter

    src = tmp_path / "tiny.gguf"
    writer = GGUFWriter(str(src), "qwen2")
    writer.add_block_count(4)
    writer.add_uint32("qwen2.embedding_length", 4)
    writer.add_tensor("token_embd.weight", np.arange(32, dtype=np.float32).reshape(8, 4))
    for i in range(4):
        writer.add_tensor(f"blk.{i}.attn_q.weight", np.full((4, 4), float(i), dtype=np.float32))
    writer.add_tensor("output_norm.weight", np.ones(4, dtype=np.float32))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    dst = tmp_path / "pruned.gguf"
    manifest = prune_gguf_layers.prune(src, dst, drop=[1, 2])
    reader = GGUFReader(str(dst))
    field = reader.fields["qwen2.block_count"]
    assert int(field.parts[field.data[0]][0]) == 2
    tensors = {t.name: t for t in reader.tensors}
    assert set(tensors) == {"token_embd.weight", "blk.0.attn_q.weight", "blk.1.attn_q.weight",
                            "output_norm.weight"}
    assert float(tensors["blk.1.attn_q.weight"].data.reshape(-1)[0]) == 3.0  # old layer 3
    assert manifest["kept_layers"] == [0, 3]
    assert manifest["params_count"] == 32 + 2 * 16 + 4


screen_metadata = _load("screen_metadata")


def test_parameter_estimate_label_rounds_like_the_profiler_expects():
    assert screen_metadata.parameter_estimate_label(1_543_714_304) == "1.54B"
    assert screen_metadata.parameter_estimate_label(1_216_129_536) == "1.22B"
    assert screen_metadata.parameter_estimate_label(752_393_024) == "752M"


def test_build_metadata_replaces_only_the_model_block_and_runtime_path():
    base = {"team_id": "muta", "model": {"name": "old", "runtime": "llama.cpp",
            "quantization": "GGUF Q4_K_M", "parameters_estimate": "1.54B",
            "packaging": "binary_bundle"}, "_runtime": {"model_path": "model/old.gguf"}}
    meta = screen_metadata.build_metadata(
        base, "unhealed-21L-contiguous.gguf", 1_216_129_536, "GGUF Q4_K_M"
    )
    assert meta["team_id"] == "muta"
    assert meta["model"] == {"name": "unhealed-21L-contiguous.gguf", "runtime": "llama.cpp",
                             "quantization": "GGUF Q4_K_M", "parameters_estimate": "1.22B",
                             "packaging": "binary_bundle"}
    assert meta["_runtime"] == {"model_path": "model/unhealed-21L-contiguous.gguf"}


score_candidates = _load("score_candidates")


def _audit(tps, peak, arc):
    return {"throughput": {"tokens_per_second_generation": tps, "first_token_latency_ms": 1.0},
            "memory": {"peak_rss_mb": peak, "steady_state_rss_mb": peak},
            "accuracy": [{"benchmark": "arc_easy", "samples": 50, "score": arc}],
            "cpu_thermal": {"core_temp_c_peak": None, "throttled": False, "cpu_percent_p99": 70.0},
            "model_info": {"params_count": 1, "params_match": True}}


def test_break_even_matches_the_exchange_rates():
    control = score_candidates.row_from_audit("control", _audit(5.77, 1099.54, 0.84))
    cand = score_candidates.row_from_audit("21L", _audit(7.32, 885.5, 0.70))
    # ΔS_perf = (7.32-5.77)/15*100 = 10.33 → ×0.3 = 3.10
    # ΔS_eff = (1099.54-885.5)/7000*100 = 3.06 → ×0.2 = 0.61
    assert score_candidates.break_even_accuracy_loss(control, cand) == pytest.approx(7.42, abs=0.01)
    assert cand["S_total_arc50"] == pytest.approx(0.5 * 70 + 0.3 * 48.8 + 0.2 * 87.35, abs=0.05)


def test_shortlist_keeps_depths_whose_floor_is_within_twice_break_even():
    control = score_candidates.row_from_audit("control", _audit(5.77, 1099.54, 0.84))
    rows = [
        score_candidates.row_from_audit("unhealed-24L-contiguous", _audit(6.57, 977.0, 0.82)),
        score_candidates.row_from_audit("unhealed-21L-contiguous", _audit(7.32, 885.5, 0.72)),
        score_candidates.row_from_audit("unhealed-21L-lowest_bi", _audit(7.30, 885.5, 0.66)),
        score_candidates.row_from_audit("unhealed-17L-contiguous", _audit(8.66, 764.0, 0.40)),
    ]
    picked = score_candidates.shortlist(rows, control, max_depths=2)
    # 17L fails the 2×break-even floor (loss 44 > 27); 21L-lowest_bi loses to 21L-contiguous
    # (same depth, lower total); survivors rank by unhealed S_total: 24L (71.35) then 21L (68.11).
    assert [r["name"] for r in picked] == ["unhealed-24L-contiguous", "unhealed-21L-contiguous"]


def test_verdict_requires_both_totals_gsm8k_and_fraud_check():
    published = {"S_total_arc500": 70.0, "S_total_judge": 47.0, "gsm8k_40": 0.50}
    good = {"S_total_arc500": 71.5, "S_total_judge": 48.5, "gsm8k_40": 0.47, "params_match": True}
    assert score_candidates.verdict(good, published)["promote"] is True
    bad = dict(good, gsm8k_40=0.40)
    assert score_candidates.verdict(bad, published)["promote"] is False


prune_hf_layers = _load("prune_hf_layers")  # torch is imported inside its functions


def test_prune_model_keeps_the_right_layer_objects_and_still_runs():
    torch = pytest.importorskip("torch")  # inside the test, never at module level
    pytest.importorskip("transformers")
    from transformers import Qwen2Config, Qwen2ForCausalLM

    config = Qwen2Config(
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=4,
        num_attention_heads=4,
        num_key_value_heads=2,
        vocab_size=128,
        max_position_embeddings=64,
        tie_word_embeddings=True,
    )
    torch.manual_seed(0)
    model = Qwen2ForCausalLM(config).eval()
    original = list(model.model.layers)
    kept = prune_hf_layers.prune_model(model, drop=[1, 2])
    assert kept == [0, 3]
    assert model.config.num_hidden_layers == 2
    assert model.model.layers[0] is original[0] and model.model.layers[1] is original[3]
    assert model.model.layers[1].self_attn.layer_idx == 1
    ids = torch.tensor([[1, 2, 3, 4]])
    with torch.no_grad():
        logits = model(input_ids=ids, use_cache=False).logits
    assert logits.shape == (1, 4, 128) and torch.isfinite(logits).all()


accuracy_battery = _load("accuracy_battery")


def test_parse_tasks_splits_name_and_limit():
    assert accuracy_battery.parse_tasks("arc_easy:500, gsm8k:40") == [
        ("arc_easy", 500),
        ("gsm8k", 40),
    ]

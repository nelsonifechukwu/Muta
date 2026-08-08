"""The TTFT preamble model: tokenizer, forward pass, generation, and absence.

The numeric fidelity of the port was established against HF transformers (max |Δlogit|
8.6e-05 over prefill, KV-cache and past-window-local prompts; greedy output
token-identical) — RESULTS.md 2026-08-08. transformers/torch are not backend dependencies,
so what is guarded *here* is everything reachable without them: exact behaviours that would
silently rot (tokenizer round-trip, cache equivalence, determinism) and the degradation
path that runs on every box where the model is not provisioned.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from runtime.ttft import (
    ByteBPE,
    IncrementalText,
    PreambleModel,
    PreambleWriter,
    load_torch_state_dict,
)

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "ttft"
provisioned = pytest.mark.skipif(
    not (MODEL_DIR / "ttft-model.npz").is_file(),
    reason="TTFT model not provisioned (scripts/fetch_ttft_model.py)",
)


# --- degradation: the path most deployments take ---------------------------------------


def test_load_returns_none_when_absent(tmp_path):
    """A missing preamble model disables the preamble. It must never raise: the feature is
    an enhancement, and the tutor works without it."""
    assert PreambleModel.load(tmp_path) is None
    assert PreambleWriter.load(tmp_path) is None


def test_load_returns_none_when_corrupt(tmp_path):
    (tmp_path / "ttft-model.npz").write_bytes(b"not an npz")
    (tmp_path / "ttft-config.json").write_text("{}")
    assert PreambleModel.load(tmp_path) is None


def test_load_returns_none_when_tokenizer_missing(tmp_path):
    """Weights without vocab/merges is a half-provisioned directory, not a usable model."""
    real = MODEL_DIR / "ttft-model.npz"
    if not real.is_file():
        pytest.skip("TTFT model not provisioned")
    (tmp_path / "ttft-model.npz").write_bytes(real.read_bytes())
    (tmp_path / "ttft-config.json").write_text((MODEL_DIR / "ttft-config.json").read_text())
    assert PreambleWriter.load(tmp_path) is None


# --- incremental utf-8 -----------------------------------------------------------------


def test_incremental_text_holds_back_split_utf8():
    """A BPE token can end mid-codepoint; the UI must never receive U+FFFD for that."""
    inc = IncrementalText()
    blob = "π≈3.14159".encode("utf-8")
    out = "".join(inc.push(blob[i : i + 1]) for i in range(len(blob)))
    assert out == "π≈3.14159"


def test_incremental_text_emits_complete_prefix():
    inc = IncrementalText()
    assert inc.push("ab".encode()) == "ab"
    assert inc.push("π".encode()[:1]) == ""  # incomplete — held
    assert inc.push("π".encode()[1:]) == "π"


# --- tokenizer -------------------------------------------------------------------------


@provisioned
def test_tokenizer_round_trips():
    tok = ByteBPE.load(MODEL_DIR)
    for text in ("Once upon a time", " a little girl named Lily.", "3 + 4 = 7"):
        ids = tok.encode(text)
        back = b"".join(tok.decode_bytes(i) for i in ids).decode("utf-8")
        assert back == text


@provisioned
def test_tokenizer_matches_pinned_gpt2_ids():
    """Pinned against HF's GPT-2/Neo tokenizer output. These ids are the contract: if the
    pre-tokenizer regex or merge order drifts, the model reads a different prompt."""
    tok = ByteBPE.load(MODEL_DIR)
    assert tok.encode("Once upon a time there was") == [7454, 2402, 257, 640, 612, 373]


# --- forward pass ----------------------------------------------------------------------


@provisioned
def test_kv_cache_matches_full_prefill():
    """Incremental decode through the cache must equal re-running the whole prefix — the
    property that makes the cache an optimisation rather than a second model."""
    model = PreambleModel.load(MODEL_DIR)
    tok = ByteBPE.load(MODEL_DIR)
    ids = tok.encode("Once upon a time there was a little girl named Lily")

    cache = model.empty_cache()
    full = model.forward(np.array(ids), cache, 0)

    cache = model.empty_cache()
    model.forward(np.array(ids[:-1]), cache, 0)
    incremental = model.forward(np.array(ids[-1:]), cache, len(ids) - 1)

    assert np.abs(full - incremental).max() < 1e-4


@provisioned
def test_local_attention_window_is_bounded():
    """Layers marked `local` see at most `window_size` tokens. Change the token that falls
    just outside the window and the logits must not move; change one inside and they must.
    This is the one GPT-Neo-specific behaviour a GPT-2 port silently gets wrong."""
    model = PreambleModel.load(MODEL_DIR)
    window = model.cfg.window_size
    rng = np.random.default_rng(0)
    ids = rng.integers(0, 50257, size=window + 40).tolist()

    def logits(seq):
        return model.forward(np.array(seq), model.empty_cache(), 0)

    base = logits(ids)
    outside = list(ids)
    outside[0] = (outside[0] + 1) % 50257  # >window tokens back: local layers cannot see it
    inside = list(ids)
    inside[-2] = (inside[-2] + 1) % 50257

    assert np.abs(logits(outside) - base).max() < np.abs(logits(inside) - base).max()


@provisioned
def test_attention_logits_are_unscaled():
    """GPT-Neo does not divide attention scores by sqrt(head_dim). The guard is behavioural:
    a scaled implementation drifts off the pinned greedy continuation immediately."""
    model = PreambleModel.load(MODEL_DIR)
    tok = ByteBPE.load(MODEL_DIR)
    out = list(model.generate(tok.encode("Once upon a time there was"), max_tokens=8, temperature=0.0))
    text = b"".join(tok.decode_bytes(t) for t in out).decode("utf-8")
    assert text == " a little girl named Lily. She loved"


# --- generation ------------------------------------------------------------------------


@provisioned
def test_generation_is_deterministic_under_seed():
    writer = PreambleWriter.load(MODEL_DIR)
    a = "".join(writer.stream("Once upon a time", max_tokens=24, seed=7))
    b = "".join(writer.stream("Once upon a time", max_tokens=24, seed=7))
    assert a == b and a.strip()


@provisioned
def test_generation_respects_max_tokens():
    writer = PreambleWriter.load(MODEL_DIR)
    tok = writer.tokenizer
    text = "".join(writer.stream("Once upon a time", max_tokens=5, seed=1))
    assert 0 < len(tok.encode(text)) <= 5


@provisioned
def test_config_matches_the_pinned_checkpoint():
    cfg = json.loads((MODEL_DIR / "ttft-config.json").read_text())
    assert cfg["n_layer"] == 8 and cfg["n_head"] == 16 and cfg["n_embd"] == 64
    assert cfg["vocab_size"] == 50257 and cfg["window_size"] == 256
    assert cfg["attention_layers"] == ["global", "local"] * 4


# --- checkpoint reader -----------------------------------------------------------------


def _archive(tmp_path: Path, payload: bytes) -> Path:
    import zipfile

    archive = tmp_path / "hostile.bin"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("hostile/data.pkl", payload)
    return archive


def test_torch_reader_refuses_to_execute_a_reduce(tmp_path):
    """The unpickler is restricted by construction: `find_class` hands back data, `dict`, or
    an object that raises when called. A checkpoint carrying the classic `__reduce__`
    payload therefore fails loudly instead of running it — this reader is pointed at a file
    downloaded from the internet, so that guarantee is the point."""
    import pickle

    class _Exploit:
        def __reduce__(self):
            return (__import__("os").system, ("echo pwned",))

    # `os.system` pickles under its implementation module (`posix`/`nt`), not `os`.
    with pytest.raises(TypeError, match=r"unsupported constructor \w+\.system"):
        load_torch_state_dict(_archive(tmp_path, pickle.dumps(_Exploit())))


def test_torch_reader_ignores_non_tensor_entries(tmp_path):
    """A bare reference to a callable is never invoked, and nothing that is not an array
    survives into the returned state dict."""
    import pickle

    archive = _archive(tmp_path, pickle.dumps({"x": __import__("os").system, "n": 1}))
    assert load_torch_state_dict(archive) == {}

"""The TTFT model: a NumPy GPT-Neo that answers *first*, in milliseconds.

Why this exists
---------------
The 4B's time-to-first-token is dominated by prefill. On the 8 GB x86 target that is
seconds on the first turn of a conversation, and a student staring at an empty pane reads
it as "broken", not "thinking". This module runs a ~3.6 M-parameter GPT-Neo (TinyStories-1M)
in-process to put *something* on screen inside a few milliseconds while llama-server
prefills, and gets out of the way the moment the real first token lands.

Why NumPy and not llama.cpp
---------------------------
TinyStories-1M is `GPTNeoForCausalLM` (`model_type: gpt_neo`) — GPT-2-shaped, but with
alternating global/local attention and *unscaled* attention logits. llama.cpp's converter
registers `GPTNeoXForCausalLM` and `GPT2LMHeadModel`; plain GPT-Neo is in neither, and no
usable GGUF of it exists on the Hub (the one repo that claims to is empty). The options
were: patch a pinned engine (b10035 is pinned for a reason), stand up a third llama-server
for 14 MB of weights, or run 8 layers of hidden-size 64 in the `numpy` we already depend
on. At this size the third option is not a compromise — a decode step is a handful of
64-wide GEMVs, which is far below the cost of the HTTP round-trip the alternatives add.

The one behaviour to keep in mind
---------------------------------
This model was trained on toddler stories. It cannot tutor, and nothing here pretends it
can: its output is streamed as a distinct `preamble` event, is never persisted as assistant
content, and never contributes to the reported `ttft_s`. See docs/ttft-preamble.md.
"""

from __future__ import annotations

import json
import logging
import pickle
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Storage classes torch writes into a .bin checkpoint, mapped to the numpy dtype that reads
# the raw buffer back. Little-endian is pinned explicitly: the pickle carries no byte order
# and every target this ships to is LE, so an implicit native dtype would be a silent trap
# on the day someone runs it elsewhere.
_TORCH_DTYPES = {
    "FloatStorage": np.dtype("<f4"),
    "HalfStorage": np.dtype("<f2"),
    "DoubleStorage": np.dtype("<f8"),
    "LongStorage": np.dtype("<i8"),
    "IntStorage": np.dtype("<i4"),
    "ByteStorage": np.dtype("u1"),
    "BoolStorage": np.dtype("?"),
}


class _Opaque:
    """Stand-in for a torch class we never call. Named so a surprise shows up in the error."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, *a, **k):  # pragma: no cover - defensive
        raise TypeError(f"checkpoint calls unsupported constructor {self.name}")


def load_torch_state_dict(path: Path) -> dict[str, np.ndarray]:
    """Read a torch `.bin` checkpoint with numpy only — no torch in the backend image.

    A modern torch save is a zip: `<root>/data.pkl` is a pickle whose persistent ids name
    raw storage blobs under `<root>/data/<key>`. Unpickling it needs exactly two hooks —
    `persistent_load` to resolve a storage id, and `_rebuild_tensor_v2` to turn
    (storage, offset, shape) into an array. Everything else in the stream is an
    OrderedDict. The unpickler is restricted by construction: `find_class` returns data,
    `dict`, or an object that raises, so a hostile checkpoint has nothing to call.
    """
    zf = zipfile.ZipFile(path)
    root = zf.namelist()[0].split("/", 1)[0]

    def rebuild_tensor(storage, offset, size, stride, *_rest):
        dtype, key = storage
        flat = np.frombuffer(zf.read(f"{root}/data/{key}"), dtype=dtype)
        count = int(np.prod(size)) if size else 1
        # Views into the zip's decompressed bytes are read-only; copy so callers can
        # rescale weights in place (the q-projection prescale below does exactly that).
        return flat[offset : offset + count].reshape(size).copy()

    class _Unpickler(pickle.Unpickler):
        def find_class(self, module: str, name: str):
            if name == "_rebuild_tensor_v2":
                return rebuild_tensor
            if name in _TORCH_DTYPES:
                return _TORCH_DTYPES[name]
            if (module, name) == ("collections", "OrderedDict"):
                return dict
            return _Opaque(f"{module}.{name}")

        def persistent_load(self, pid):
            kind, storage_type, key, _location, _numel = pid
            if kind != "storage":
                raise ValueError(f"unsupported persistent id {kind!r}")
            return storage_type, key

    with zf.open(f"{root}/data.pkl") as fh:
        state = _Unpickler(fh).load()
    return {k: v for k, v in state.items() if isinstance(v, np.ndarray)}


# --------------------------------------------------------------------------------------
# Tokenizer — GPT-2 byte-level BPE (TinyStories uses EleutherAI/gpt-neo-125M's vocab)
# --------------------------------------------------------------------------------------

# GPT-2's pre-tokenizer. Kept verbatim (contractions, then letters / digits / symbols /
# trailing space) because a "cleaner" regex changes the token ids and therefore the text.
_PRETOKEN = re.compile(
    r"'s|'t|'re|'ve|'m|'ll|'d| ?[A-Za-z]+| ?[0-9]+| ?[^\sA-Za-z0-9]+|\s+(?!\S)|\s+"
)


@lru_cache(maxsize=1)
def _byte_encoder() -> dict[int, str]:
    """GPT-2's bytes->unicode table: every byte gets a printable codepoint so the BPE
    merges (and vocab.json) can be plain text."""
    printable = list(range(ord("!"), ord("~") + 1))
    printable += list(range(ord("\xa1"), ord("\xac") + 1))
    printable += list(range(ord("\xae"), ord("\xff") + 1))
    mapped = printable[:]
    spare = 0
    for b in range(256):
        if b not in printable:
            printable.append(b)
            mapped.append(256 + spare)
            spare += 1
    return {b: chr(c) for b, c in zip(printable, mapped)}


class ByteBPE:
    """Just enough GPT-2 BPE to seed a prompt and stream the output back as text."""

    def __init__(self, vocab: dict[str, int], merges: list[tuple[str, str]]) -> None:
        self.vocab = vocab
        self.decoder = {i: t for t, i in vocab.items()}
        self.ranks = {pair: i for i, pair in enumerate(merges)}
        self.b2u = _byte_encoder()
        self.u2b = {u: b for b, u in self.b2u.items()}
        self._cache: dict[str, list[str]] = {}

    @classmethod
    def load(cls, directory: Path) -> ByteBPE:
        vocab = json.loads((directory / "vocab.json").read_text(encoding="utf-8"))
        lines = (directory / "merges.txt").read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("#version"):
            lines = lines[1:]
        merges = [tuple(ln.split()) for ln in lines if len(ln.split()) == 2]
        return cls(vocab, merges)  # type: ignore[arg-type]

    def _bpe(self, token: str) -> list[str]:
        if token in self._cache:
            return self._cache[token]
        word = list(token)
        while len(word) > 1:
            pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
            best = min(pairs, key=lambda p: self.ranks.get(p, np.inf))
            if best not in self.ranks:
                break
            merged: list[str] = []
            i = 0
            while i < len(word):
                if i < len(word) - 1 and (word[i], word[i + 1]) == best:
                    merged.append(word[i] + word[i + 1])
                    i += 2
                else:
                    merged.append(word[i])
                    i += 1
            word = merged
        self._cache[token] = word
        return word

    def encode(self, text: str) -> list[int]:
        ids: list[int] = []
        for chunk in _PRETOKEN.findall(text):
            mapped = "".join(self.b2u[b] for b in chunk.encode("utf-8"))
            ids += [self.vocab[piece] for piece in self._bpe(mapped) if piece in self.vocab]
        return ids

    def decode_bytes(self, token_id: int) -> bytes:
        piece = self.decoder.get(int(token_id), "")
        return bytes(self.u2b[c] for c in piece if c in self.u2b)


class IncrementalText:
    """Byte-accumulating decoder: a BPE token can end mid-UTF-8, so hold the tail back
    until it completes rather than emitting a replacement character into the UI."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def push(self, chunk: bytes) -> str:
        self._buf += chunk
        for cut in range(len(self._buf), max(len(self._buf) - 4, -1), -1):
            try:
                text = self._buf[:cut].decode("utf-8")
            except UnicodeDecodeError:
                continue
            del self._buf[:cut]
            return text
        return ""


# --------------------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PreambleConfig:
    n_layer: int
    n_head: int
    n_embd: int
    vocab_size: int
    max_positions: int
    window_size: int
    attention_layers: tuple[str, ...]
    layer_norm_eps: float

    @classmethod
    def from_hf(cls, cfg: dict) -> PreambleConfig:
        layers = tuple(cfg["attention_layers"])
        return cls(
            n_layer=int(cfg["num_layers"]),
            n_head=int(cfg["num_heads"]),
            n_embd=int(cfg["hidden_size"]),
            vocab_size=int(cfg["vocab_size"]),
            max_positions=int(cfg["max_position_embeddings"]),
            window_size=int(cfg.get("window_size", 256)),
            attention_layers=layers,
            layer_norm_eps=float(cfg.get("layer_norm_epsilon", 1e-5)),
        )


def _layer_norm(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float) -> np.ndarray:
    mu = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + eps) * w + b


def _gelu_new(x: np.ndarray) -> np.ndarray:
    """The tanh approximation HF calls `gelu_new` — matching it exactly matters, because a
    1 M-parameter model has no capacity to absorb an activation that is merely close."""
    return 0.5 * x * (1.0 + np.tanh(0.7978845608028654 * (x + 0.044715 * x**3)))


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(-1, keepdims=True)
    np.exp(x, out=x)
    return x / x.sum(-1, keepdims=True)


class PreambleModel:
    """GPT-Neo forward pass in NumPy, with a KV cache, at batch size 1."""

    def __init__(self, weights: dict[str, np.ndarray], config: PreambleConfig) -> None:
        self.w = weights
        self.cfg = config
        self.head_dim = config.n_embd // config.n_head

    # -- loading ---------------------------------------------------------------------
    @classmethod
    def load(cls, directory: Path | str) -> PreambleModel | None:
        """Load from a converted `.npz` bundle. Returns None when the model is absent —
        the preamble is an enhancement, and a missing enhancement is not an error
        (degradation, not errors: the stream simply starts at the 4B's own first token)."""
        directory = Path(directory)
        blob = directory / "ttft-model.npz"
        cfg_path = directory / "ttft-config.json"
        if not (blob.is_file() and cfg_path.is_file()):
            log.info("TTFT preamble model not provisioned at %s — preamble disabled", directory)
            return None
        try:
            cfg = PreambleConfig(**json.loads(cfg_path.read_text()))
            with np.load(blob) as npz:
                weights = {k: npz[k] for k in npz.files}
            return cls(weights, cfg)
        except (OSError, ValueError, TypeError, KeyError) as e:
            log.warning("TTFT preamble model at %s is unusable (%r) — preamble disabled", directory, e)
            return None

    # -- forward ---------------------------------------------------------------------
    def _attention(
        self,
        layer: int,
        x: np.ndarray,
        cache: list[tuple[np.ndarray, np.ndarray]],
        past_len: int,
    ) -> np.ndarray:
        w, cfg = self.w, self.cfg
        n_new = x.shape[0]
        # Weights are stored pre-transposed (in, out), so this is a plain GEMM per call.
        q = x @ w[f"h{layer}.attn.q"]
        k = x @ w[f"h{layer}.attn.k"]
        v = x @ w[f"h{layer}.attn.v"]

        if cache[layer][0].size:
            k = np.concatenate([cache[layer][0], k], axis=0)
            v = np.concatenate([cache[layer][1], v], axis=0)
        cache[layer] = (k, v)

        total = k.shape[0]
        # (heads, seq, head_dim)
        qh = q.reshape(n_new, cfg.n_head, self.head_dim).transpose(1, 0, 2)
        kh = k.reshape(total, cfg.n_head, self.head_dim).transpose(1, 0, 2)
        vh = v.reshape(total, cfg.n_head, self.head_dim).transpose(1, 0, 2)

        # GPT-Neo does NOT divide by sqrt(head_dim) — unlike GPT-2 and every llama-family
        # model. Scaling here would quietly flatten the distribution and turn the output
        # into mush that still *looks* like English.
        scores = qh @ kh.transpose(0, 2, 1)

        rows = np.arange(past_len, past_len + n_new)[:, None]
        cols = np.arange(total)[None, :]
        allowed = cols <= rows
        if cfg.attention_layers[layer] == "local":
            # HF builds the local mask as tril ^ tril(-window): a position attends to the
            # `window_size` tokens ending at itself, so the earliest visible column is
            # row - window + 1.
            allowed &= cols > rows - cfg.window_size
        scores = np.where(allowed, scores, np.float32(-1e30))

        out = (_softmax(scores) @ vh).transpose(1, 0, 2).reshape(n_new, cfg.n_embd)
        return out @ w[f"h{layer}.attn.o"] + w[f"h{layer}.attn.o.b"]

    def forward(
        self,
        tokens: np.ndarray,
        cache: list[tuple[np.ndarray, np.ndarray]],
        past_len: int,
    ) -> np.ndarray:
        """Logits for the final position only — nothing here ever needs the others."""
        w, cfg = self.w, self.cfg
        positions = np.arange(past_len, past_len + len(tokens))
        x = (w["wte"][tokens] + w["wpe"][positions]).astype(np.float32)

        for i in range(cfg.n_layer):
            h = _layer_norm(x, w[f"h{i}.ln_1.w"], w[f"h{i}.ln_1.b"], cfg.layer_norm_eps)
            x = x + self._attention(i, h, cache, past_len)
            h = _layer_norm(x, w[f"h{i}.ln_2.w"], w[f"h{i}.ln_2.b"], cfg.layer_norm_eps)
            h = _gelu_new(h @ w[f"h{i}.mlp.fc"] + w[f"h{i}.mlp.fc.b"])
            x = x + (h @ w[f"h{i}.mlp.proj"] + w[f"h{i}.mlp.proj.b"])

        x = _layer_norm(x[-1:], w["ln_f.w"], w["ln_f.b"], cfg.layer_norm_eps)
        return (x @ w["wte"].T)[0]  # lm_head is tied to the embedding

    def empty_cache(self) -> list[tuple[np.ndarray, np.ndarray]]:
        empty = np.empty((0, self.cfg.n_embd), dtype=np.float32)
        return [(empty, empty) for _ in range(self.cfg.n_layer)]

    # -- generation ------------------------------------------------------------------
    def generate(
        self,
        prompt_ids: list[int],
        *,
        max_tokens: int = 48,
        temperature: float = 0.8,
        top_k: int = 40,
        seed: int | None = None,
        eos_id: int = 50256,
    ) -> Iterator[int]:
        """Yield token ids one at a time. Deterministic when `seed` is given, which is what
        makes the preamble testable at all."""
        rng = np.random.default_rng(seed)
        cache = self.empty_cache()
        ids = list(prompt_ids) or [eos_id]
        logits = self.forward(np.array(ids), cache, 0)
        past = len(ids)

        for _ in range(max_tokens):
            if temperature <= 0:
                nxt = int(logits.argmax())
            else:
                scaled = logits / temperature
                if 0 < top_k < scaled.size:
                    cut = np.partition(scaled, -top_k)[-top_k]
                    scaled = np.where(scaled < cut, -np.inf, scaled)
                probs = _softmax(scaled.astype(np.float64))
                nxt = int(rng.choice(probs.size, p=probs))
            if nxt == eos_id or past >= self.cfg.max_positions:
                return
            yield nxt
            logits = self.forward(np.array([nxt]), cache, past)
            past += 1


class PreambleWriter:
    """Model + tokenizer + the house style rules for what a preamble may look like."""

    def __init__(self, model: PreambleModel, tokenizer: ByteBPE) -> None:
        self.model = model
        self.tokenizer = tokenizer

    @classmethod
    def load(cls, directory: Path | str) -> PreambleWriter | None:
        directory = Path(directory)
        model = PreambleModel.load(directory)
        if model is None:
            return None
        try:
            return cls(model, ByteBPE.load(directory))
        except (OSError, KeyError, ValueError) as e:
            log.warning("TTFT tokenizer at %s is unusable (%r) — preamble disabled", directory, e)
            return None

    def warmup(self) -> None:
        """Pay the one-off costs now instead of on a student's first turn.

        Measured on the M2 dev host: the first generation after load takes 32 ms and every
        one after it 1.6 ms. The difference is the BPE merge table materialising, the npz's
        pages being touched, and BLAS initialising — all of it one-time, and all of it
        landing on precisely the request this feature exists to make feel fast.
        """
        for _ in self.stream("Once upon a time", max_tokens=2, temperature=0.0):
            pass

    def stream(
        self,
        seed_text: str = "",
        *,
        max_tokens: int = 48,
        temperature: float = 0.8,
        seed: int | None = None,
    ) -> Iterator[str]:
        """Stream preamble text. The first chunk is what the student sees first, so the
        prompt is prefilled here and nothing is buffered on the way out."""
        prompt_ids = self.tokenizer.encode(seed_text) if seed_text else []
        text = IncrementalText()
        for token_id in self.model.generate(
            prompt_ids, max_tokens=max_tokens, temperature=temperature, seed=seed
        ):
            chunk = text.push(self.tokenizer.decode_bytes(token_id))
            if chunk:
                yield chunk

#!/usr/bin/env python3
"""Provision the TTFT preamble model (TinyStories-1M) into `models/ttft/`.

Build-machine only, like `fetch_models.py`: it resolves a pinned revision, verifies every
file by sha256, and converts the torch checkpoint into the `.npz` that `runtime/ttft.py`
loads. Nothing it writes needs the network at run time.

Why this is a separate script and not an entry in `model_specs.ARTIFACTS`
------------------------------------------------------------------------
`fetch_models.py` enforces the §13 redistribution policy: permissive licence or refuse.
`roneneldan/TinyStories-1M` **declares no licence at all** — no `license:` tag, no LICENSE
file, nothing in either README. Adding it to the artifact table would mean either
weakening that gate for everything or writing a licence claim we cannot support. So the
preamble model lives here, opt-in, and the honest status is stated up front:

    NOT CLEARED FOR REDISTRIBUTION. Fetch it for development and measurement. Before it
    ships in a bundle, either the upstream licence gets resolved or the weights get
    swapped (see docs/ttft-preamble.md — the runner is architecture-generic GPT-Neo).

Usage:
    python scripts/fetch_ttft_model.py                 # fetch + convert into models/ttft
    python scripts/fetch_ttft_model.py --dest models/ttft --revision <sha>
    python scripts/fetch_ttft_model.py --print-hashes  # emit the sha256 pin block
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.ttft import load_torch_state_dict  # noqa: E402

REPO = "roneneldan/TinyStories-1M"
# Pinned so a re-run fetches byte-identical files. Re-resolve with --revision main and
# --print-hashes if upstream ever moves; a moved pin must be re-verified, not assumed.
REVISION = "77f1b168e219585646439073245fe87e56b3023e"
FILES = ("config.json", "pytorch_model.bin", "vocab.json", "merges.txt")

# sha256 of each pinned file, checked after download and again after the copy into models/.
EXPECTED = {
    "config.json": "ff74c30d5ebb5ab1da0f2ea479adf7197c504b42b5522a858c334ab91ed4958c",
    "pytorch_model.bin": "07f9609ea882b8163ff3b23d40e2b82cb715d409631beb15c84b164f3877dae7",
    "vocab.json": "3ba3c3109ff33976c4bd966589c11ee14fcaa1f4c9e5e154c2ed7f99d80709e7",
    "merges.txt": "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
}

LICENCE_BANNER = """
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  LICENCE UNRESOLVED — development and measurement only.                  │
  │  roneneldan/TinyStories-1M declares no licence (no tag, no LICENSE file).│
  │  Do NOT ship these weights in a bundle until that is resolved.           │
  │  See docs/ttft-preamble.md for the swap path.                            │
  └──────────────────────────────────────────────────────────────────────────┘
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(dest: Path, revision: str) -> dict[str, Path]:
    from huggingface_hub import hf_hub_download

    out: dict[str, Path] = {}
    for name in FILES:
        print(f"  fetching {name} …", flush=True)
        out[name] = Path(
            hf_hub_download(REPO, name, revision=revision, cache_dir=str(dest / ".cache"))
        )
    return out


def verify(paths: dict[str, Path], *, strict: bool) -> None:
    for name, path in paths.items():
        digest = sha256(path)
        expected = EXPECTED.get(name) or ""
        if not expected:
            print(f"  {name}: sha256={digest} (no pin recorded)")
            continue
        if digest != expected:
            raise SystemExit(f"FATAL: {name} sha256 {digest} != pinned {expected}")
        if strict:
            print(f"  {name}: sha256 ok")


def convert(state: dict[str, np.ndarray], cfg: dict) -> dict[str, np.ndarray]:
    """GPT-Neo state dict -> the flat, pre-transposed arrays `runtime/ttft.py` expects.

    Two deliberate transforms:
      * `nn.Linear` stores (out, in); every weight is transposed once here so the hot path
        is a plain `x @ W` instead of a transpose per token per layer.
      * the `attn.attention.bias` causal masks are dropped. They are 2048x2048 bool buffers
        — 33.5 M of the checkpoint's 37.3 M elements, ~90% of the file — and the runner
        builds its mask arithmetically. Keeping them would make a 14 MB model a 48 MB one.
    """
    n_layer = int(cfg["num_layers"])
    out: dict[str, np.ndarray] = {
        "wte": state["transformer.wte.weight"].astype(np.float32),
        "wpe": state["transformer.wpe.weight"].astype(np.float32),
        "ln_f.w": state["transformer.ln_f.weight"].astype(np.float32),
        "ln_f.b": state["transformer.ln_f.bias"].astype(np.float32),
    }
    for i in range(n_layer):
        p = f"transformer.h.{i}"
        a = f"{p}.attn.attention"
        out[f"h{i}.ln_1.w"] = state[f"{p}.ln_1.weight"].astype(np.float32)
        out[f"h{i}.ln_1.b"] = state[f"{p}.ln_1.bias"].astype(np.float32)
        out[f"h{i}.ln_2.w"] = state[f"{p}.ln_2.weight"].astype(np.float32)
        out[f"h{i}.ln_2.b"] = state[f"{p}.ln_2.bias"].astype(np.float32)
        out[f"h{i}.attn.q"] = state[f"{a}.q_proj.weight"].T.astype(np.float32)
        out[f"h{i}.attn.k"] = state[f"{a}.k_proj.weight"].T.astype(np.float32)
        out[f"h{i}.attn.v"] = state[f"{a}.v_proj.weight"].T.astype(np.float32)
        out[f"h{i}.attn.o"] = state[f"{a}.out_proj.weight"].T.astype(np.float32)
        out[f"h{i}.attn.o.b"] = state[f"{a}.out_proj.bias"].astype(np.float32)
        out[f"h{i}.mlp.fc"] = state[f"{p}.mlp.c_fc.weight"].T.astype(np.float32)
        out[f"h{i}.mlp.fc.b"] = state[f"{p}.mlp.c_fc.bias"].astype(np.float32)
        out[f"h{i}.mlp.proj"] = state[f"{p}.mlp.c_proj.weight"].T.astype(np.float32)
        out[f"h{i}.mlp.proj.b"] = state[f"{p}.mlp.c_proj.bias"].astype(np.float32)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=Path("models/ttft"))
    ap.add_argument("--revision", default=REVISION)
    ap.add_argument("--print-hashes", action="store_true", help="print the sha256 pin block and exit")
    ap.add_argument(
        "--keep-cache",
        action="store_true",
        help="keep the HF download cache (48 MB, makes a re-fetch resumable); it is deleted "
        "by default because only the 15 MB converted npz is needed afterwards",
    )
    args = ap.parse_args()

    print(LICENCE_BANNER)
    dest = args.dest
    dest.mkdir(parents=True, exist_ok=True)

    print(f"pin: {REPO}@{args.revision}")
    paths = download(dest, args.revision)

    if args.print_hashes:
        print("\nEXPECTED = {")
        for name, path in paths.items():
            print(f'    "{name}": "{sha256(path)}",')
        print("}")
        return 0

    verify(paths, strict=True)

    cfg_raw = json.loads(paths["config.json"].read_text())
    if cfg_raw.get("architectures") != ["GPTNeoForCausalLM"]:
        raise SystemExit(f"FATAL: unexpected architecture {cfg_raw.get('architectures')}")

    print("  converting checkpoint (torch pickle -> npz, no torch) …")
    weights = convert(load_torch_state_dict(paths["pytorch_model.bin"]), cfg_raw)

    blob = dest / "ttft-model.npz"
    np.savez(blob, **weights)
    (dest / "ttft-config.json").write_text(
        json.dumps(
            {
                "n_layer": int(cfg_raw["num_layers"]),
                "n_head": int(cfg_raw["num_heads"]),
                "n_embd": int(cfg_raw["hidden_size"]),
                "vocab_size": int(cfg_raw["vocab_size"]),
                "max_positions": int(cfg_raw["max_position_embeddings"]),
                "window_size": int(cfg_raw.get("window_size", 256)),
                "attention_layers": list(cfg_raw["attention_layers"]),
                "layer_norm_eps": float(cfg_raw.get("layer_norm_epsilon", 1e-5)),
            },
            indent=2,
        )
    )
    for name in ("vocab.json", "merges.txt"):
        (dest / name).write_bytes(paths[name].read_bytes())

    params = sum(int(v.size) for v in weights.values())
    print(f"\n  wrote {blob} — {params:,} parameters, {blob.stat().st_size / 1e6:.1f} MB on disk")
    print(f"  wrote {dest}/ttft-config.json, vocab.json, merges.txt")

    # The 48 MB checkpoint is conversion input only — 90% of it is causal-mask buffers the
    # runner never loads. Keeping it would triple the artifact's footprint for nothing.
    cache = dest / ".cache"
    if not args.keep_cache and cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)
        print("  removed the download cache (--keep-cache to keep it resumable)")
    print("\n  enable with MUTA_RT_TTFT_PREAMBLE=1 (see docs/ttft-preamble.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

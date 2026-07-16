# Smoke fixture — Qwen3-0.6B Q4_K_M

**ROADMAP deliverable: Wed 15 Jul, `[Lane B]`.**

## What and why

**`unsloth/Qwen3-0.6B-GGUF` · `Qwen3-0.6B-Q4_K_M.gguf` · 396,705,472 bytes (378 MiB).**

The fixture's job is to prove **the pipeline**, not to be good. So the criterion is *the
smallest architecturally boring model that is definitely supported* — every exotic feature is
a place a pipeline bug can hide behind a model bug.

1. **~378 MB loads in seconds** even under QEMU emulation, keeping the dev loop tight.
   Measured: **~1.6 s** to load on an M2 Mac.
2. **Plain dense transformer with standard GQA** — no vision projector, no MTP heads, no
   linear-attention layers. If it fails, the build is broken, not the model.
3. **Long supported in llama.cpp**, so failures are unambiguous.
4. **Deliberately not a shipping candidate.** Fixture must never be confused with contender —
   the bake-off (19–22 Jul) picks what ships.
5. **Qwen tokenizer family**, so it doubles as a draft-model rehearsal for speculation later.

## Deviation from the ROADMAP — read this

The ROADMAP names `Qwen/Qwen3-0.6B`. We ship **Unsloth's** GGUF instead, for a concrete
reason:

- `Qwen/Qwen3-0.6B` is **safetensors**, not GGUF — it would need conversion.
- `Qwen/Qwen3-0.6B-GGUF` **ships only Q8_0**. No Q4_K_M.
- `ggml-org/Qwen3-0.6B-GGUF` — **also only Q8_0**.
- `unsloth/Qwen3-0.6B-GGUF` **has `Qwen3-0.6B-Q4_K_M.gguf`**, and aligns with the ROADMAP's
  own Unsloth Dynamic 2.0 preference (15/18 Jul) and its Q4_K_M fixture spec.

So the substitution *satisfies* the ROADMAP's spec rather than departing from it — the named
repo cannot. `Qwen/Qwen3-0.6B` is retained as `base_repo` in
[`runtime/config.py`](../runtime/config.py) for provenance: it is the safetensors source the
GGUF was converted from.

## Q8_0 — proving the quant path

The ROADMAP also asks for **Q8_0 (~600 MB)** alongside Q4_K_M, to prove the quant path is real
rather than a single hardcoded file. `MUTA_RT_MODEL_FILE` selects between them.

> **Status: not yet pulled.** Tracked as an open item. Q4_K_M alone proves loading; it does not
> prove the *path* generalises.

## Provenance

| | |
|---|---|
| Repo | `unsloth/Qwen3-0.6B-GGUF` |
| File | `Qwen3-0.6B-Q4_K_M.gguf` |
| Size | 396,705,472 bytes |
| HF commit | `50968a44…` |
| sha256 | `ac2d9771…` |
| Base (provenance) | `Qwen/Qwen3-0.6B` |

Resolution is **local-first with an HF fallback, always yielding a local path** — the deploy
target has no network. See `resolve_model()` in [`runtime/models.py`](../runtime/models.py).
Weights are gitignored and never committed; `make model` or `./run.sh` provisions them.

## Rejected alternatives (from the ROADMAP, recorded for the report)

| Candidate | Why not |
|---|---|
| **Qwen3.5-4B** | A likely *shipping* candidate, but ships a separate `mmproj` vision file (currently breaks Ollama GGUF loading) — extra moving parts in a fixture whose job is to have none |
| **R1-Distill-1.5B** | Emits long `<think>` blocks; slow and noisy smoke runs |
| **TinyLlama** | Obsolete |
| **Anything 7B+** | Wastes days under emulation |

## Known fixture behaviour (not bugs)

Qwen3-0.6B is small enough that it follows the persona prompts only loosely — it will sometimes
state an answer outright despite `socratic` mode forbidding it. Expected. It is a pipeline
fixture, not a tutor. Do not tune prompts against it.

Qwen3 is a **hybrid reasoning** model; `enable_thinking` defaults to `false`
(`chat_template_kwargs`) for concise output and fewer tokens per reply.

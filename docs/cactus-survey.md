# Cactus survey — what transfers to Muta and what doesn't (2026-08-01)

Cactus (https://github.com/cactus-compute/cactus, YC S25) is an ARM/mobile-first
on-device inference engine: custom rotation+codebook quantization (CQ1–CQ4 +
mixed-precision CQ2.54/CQ3.26), a zero-copy computation graph, NEON/I8MM kernels,
INT8 KV cache, and cloud handoff gated by a learned confidence probe. Muta is pinned
to llama.cpp b10035 on x86-64/AVX2 — none of the code transfers; these decisions do.
Implementation: docs/plans/2026-08-01-cactus-inspired-ram-toks-optimizations.md.

## Transferable decisions

1. **Bandwidth-ceiling math.** CPU decode streams ~the whole weight file per token.
   Cactus reports % of `bandwidth / bytes-per-token` (iPhone 17 Pro: 140 of 169
   theoretical tok/s = 83%) and stops thread-tuning near the ceiling. Muta tool:
   `bench/ceiling.py`. Also predicts x86-target decode from the box's bandwidth
   before we ever touch it.
2. **Decode wants few threads.** Their GEMV (decode) path caps at 4–5 threads on
   macOS, 2 on iOS, 1 on Android — sync overhead beats bandwidth wins. Matches our
   measured barrier-synchronization fragility (RESULTS.md 2026-08-01); motivates
   probing below the P-core count.
3. **Evictable weights vs speed.** They deliberately keep weights file-backed
   (mmap, MADV hints) and accept −17% decode so the OS can evict under pressure.
   Muta's analog: llama.cpp's CPU_REPACK copies ~1.3 GiB of the 4B into anonymous
   RAM for AVX2/NEON kernels — a repack-off probe prices that trade.
4. **Embeddings tolerate low bits; the output head doesn't.** Embedding rows are
   gathered, not matmul'd — TurboQuant-H runs per-layer embeddings at 2.125 bits
   for +0.06 PPL and −40% model size. Their production recipe: embeddings 2-bit,
   LLM linears 4-bit, output head pinned at 4-bit. Qwen3.5-4B's 248,320-token
   vocab makes token_embd/output the largest tensors in our GGUF — llama-quantize's
   --token-embedding-type/--output-tensor-type is the direct analog.
5. **Mixed precision beats uniform.** "The marginal value of a bit is sharply
   non-uniform across tensors": CQ3.26 (~3.3 bpw, 68 sensitive tensors at 4-bit)
   is near-lossless while uniform 2-bit zeroes GSM8K. GGUF-ecosystem analog:
   Unsloth UD dynamic quants. Generation-heavy math tasks collapse FIRST —
   accuracy probes for any lower-bit candidate must be generative math, not MCQ.
6. **Bound long-context RAM by construction.** Their KV compaction (default on)
   caps the cache at 4096→2048 (sink-4 + recent 30% + top-KeyDiff). At our pin the
   product-layer analog is a token-budgeted history trim in ChatEngine (drop whole
   oldest turns; keep the suffix stable so checkpoint LCP reuse survives).

## Decisions Cactus validates (no change needed)

- KV at INT8, not lower: "models significantly degrade when KV cache goes below
  INT4. We keep KV at INT8 to ensure correctness" — matches our q8_0-K/f16-V.
- No speculative decoding on CPU: Cactus ships none ("No speculative decode or
  MTP, pure decode"); our 07-31/08-01 measurements found every form net-negative.
- mmap'd weights (they measured Android's mmap-degraded-to-malloc costing 4–6×
  RAM vs Apple); our --no-mmap probe was −28% decode +1 GiB. Settled.
- Prompt-prefix reuse across turns: they re-prefill only the token suffix; our
  checkpoint restore already does this (29/33 reuse).
- On-demand vision encoder: they load/run/unload per request. Muta instead keeps the selected
  model's exact projector in its sole chat engine; the former TTL-reaped auxiliary reader is
  retired from the browser path (see `docs/multimodal-decision.md`).
- Benchmark hygiene: warmup run discarded, mean of 3, peak RAM sampled inside the
  decode loop, Apple phys_footprint vs Linux RSS named per-platform — all already
  native_sweep practice.

## Not applicable / rejected

- CQ/TurboQuant-H formats themselves, NEON kernels, zero-copy graph internals,
  Metal paths: engine-internal, ARM-only, unreachable at our pin.
- Confidence-probe cloud handoff: no cloud offline. The local analog (draft model
  serving instant hints) is TDD §7.6, parked behind the D2-b admission rule.
- KV-cache start-small-and-double, sliding-window ring, KeyDiff compaction:
  llama.cpp b10035 allocates -c up front and has no compaction hook; revisit only
  on a pin move.
- Single-core decode for OS-throttle stealth: a phone/background concern; the
  tutor box is foreground and plugged in.

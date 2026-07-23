# Multimodal decisions — the open gates and what closes them

Generated from TDD §14 (the companion doc the TDD asks for) plus what the implementation
now pins down. Status as of **23 Jul 2026**.

Rule this document exists to enforce: *a gate is closed by a measurement, not by a
preference.* Every row below says what would flip it and who measures. Where the code has to
choose something today, it implements the **default** and keeps the alternative behind a
config switch — never a rewrite.

---

## The gates

| ID | Decision | Default (implemented) | Alternative | What flips it | Where it lives in code |
|---|---|---|---|---|---|
| **D1** | Core quant variant | own-imatrix Q4_K_M | stock / UD-Q4_K_XL | `score.py` argmax over the bake-off matrix | `deploy/versions.lock` (`CORE_MODEL_*`, unpinned on purpose); `BundlePaths.core_model` resolves whatever GGUF is staged rather than a hardcoded name |
| **D2** | Speculation | **c** — none | a (MTP, variant B) / b (draft model) | b needs ≥ 1.43 tok/s per GiB spent, counting the draft's dual use as hint-mode | `TUTOR_SPECULATION` in `deploy/etc/profile.env`; `runtime/profiles._speculation_flags` |
| **D3** | Vision topology | two instances (text + ephemeral vision) | one always-vision instance | upstream #21133 confirmed fixed at the pin **and** ≥ 1.1 GiB steady headroom | `runtime/vision.py`; `core_vision_command` omits the three flags mmproj disables |
| **D4** | Demo engine binary | A (mainline, pinned) | B (ik_llama) / C (OpenVINO) | on-target bench: B if ≥ 1.10× A; C only if Intel **and** it beats best-of(A,B) | `TUTOR_ENGINE_VARIANT`, `IK_LLAMA_REF=` / `OPENVINO_VERSION=` (both unpinned) |
| **D5** | Premium TTS | Piper everywhere | + Kokoro in solo-demo | solo-demo RSS ≤ 6.5 GiB with Kokoro resident | `ServingProfile.tts_engine`; ladder L2 forces Piper regardless |
| **D6** | KV cache type | q8_0 | q5_1 / q4_0 | ladder sweep shows no eval regression **and** slots gained | `TUTOR_KV_TYPE`; `runtime/kvmath.CACHE_TYPE_BYTES` prices each rung |
| **D7** | Vision process mgmt | gateway subprocess manager | llama-swap / router mode | manager > 200 LoC or 3 bugs | `runtime/vision.py` — currently ~150 LoC, 0 known bugs |
| **D8** | Embedding model | bge-small-en-v1.5 Q8_0 | multilingual-e5-small | a multilingual RAG corpus lands | `EMBED_MODEL_*` in the lock; index records the embedder identity and refuses a mismatched query |
| **D9** | mlock core weights | off (classroom) / on (solo-demo) | flip | soak shows major-fault jitter > 50 ms p95 | `TUTOR_MLOCK`; `--mlock` appears only when the profile says so, and the invocation announces it |

---

## What the implementation already settles

**D3 is settled in shape even if #21133 is fixed.** `core_vision_command` deliberately omits
`--cache-reuse`, `--slot-save-path` and `--context-shift`, and there is a test asserting their
absence. Both instances point at the *same* weight file, so the page cache shares the
read-only pages and the marginal cost is mmproj + this instance's KV. If the upstream issue
is fixed at the pin, the two-instance topology stays — it is strictly more robust, and the
TTL reaper is what returns 1.1 GiB to the degradation ladder.

**D7's budget is explicit.** The manager does spawn, health-check, TTL-reap and deny. No
queueing, no restart backoff, no warm pool — those are the features that would push it past
the 200-LoC line the TDD set as the switch-to-llama-swap trigger.

**D9's asymmetry is in the code, not in a runbook.** `--mlock` is emitted only for the
solo-demo profile, and the invocation carries a note that mlock is valid only after staging
to local disk (C-4): mlocking pages that are being read from USB is the worst of both.

---

## Deviations from the TDD, and why

1. **Renderer address-space limit is 1024 MiB, not the 256 MiB of §7.5.** NumPy and
   Matplotlib reserve far more *virtual* address space at import than they ever touch. At
   256 MiB the renderer fails at `import`, which makes the diagram path permanently dead
   rather than bounded. The verifier keeps the TDD's 256 MiB, where it is comfortable.
   [MEASURE: peak RSS of one render on the target box, T8.]

2. **`python -s -S`, not `python -I -S`.** `-I` implies `-E`, which discards the `PYTHONPATH`
   the sandbox builds — the worker then cannot import SymPy at all, and every verification
   degrades to a string comparison that *looks* like it worked. The environment is replaced
   wholesale anyway, so there is nothing to inherit.

3. **`/v1/tutor/chat` is JSON; SSE lives at `/v1/tutor/chat/stream`.** One operation cannot
   honestly declare two response media types in an OpenAPI document, and the contract is the
   artifact every other lane binds to.

4. **The §7.2 endpoints are additive.** The original `/v1/chat`, `/v1/verify` and friends
   still exist and still work — the TUI and `bench/` bind to them. Contract rule is
   additive-only from 1 Aug; this landed before that.

---

## Still open, and honest about it

- **Every `[MEASURE]` in the TDD is still a planning value.** Nothing in this repo has run on
  the target x86 box. The compute-buffer figure in the KV budget table is marked PROVISIONAL
  in the generated document itself, and `--buffers-mib` exists to replace it with a measured
  one.
- **Retrieval quality is unmeasured.** T11's "top-3 recall ≥ 90% on 50 seeded queries" is
  implemented as a test, but against a lexical test-double embedder — it proves the path, not
  bge-small's recall. The real number needs the embed server and the real corpus.
- **sherpa-onnx is not vendored yet**, so ASR/TTS report `available: false` and the gateway
  degrades to text. The math-to-speech normaliser (the part that is pure logic) is done and
  golden-tested.

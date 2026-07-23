# TDD — Offline Exam-Grade Tutor: System Architecture
**Version:** 1.0-draft · **Date:** 2026-07-23 · **Status:** Ready for implementation
**Scope:** Full system architecture — models, memory, inference engines, orchestration, deployment
**Companion docs:** `README.md` (product), `ROADMAP.md` (schedule), `/docs/multimodal-decision.md` (to be generated from §14)

---

## 0. How to use this document (instructions for Claude Code)

This TDD is the single source of truth for implementation. Rules of engagement:

1. **Implementation order** is §15. Do not implement out of order unless a task's dependencies are already satisfied.
2. **Conventions used throughout:**
   - `[MEASURE: cmd]` — a value that MUST be obtained by running the given command on real hardware. Never invent these numbers. Until measured, use the stated planning value and log it as provisional in `bench/results.csv`.
   - `[VERIFY-AT-PIN]` — a behavior that must be confirmed against the pinned llama.cpp commit before relying on it (flag names and server behaviors drift between releases).
   - `[GATE: Dn]` — blocked on decision `Dn` in the Decision Register (§14). Implement the default path; keep the alternative behind a config switch.
3. **Two-scoreboards rule (governs everything):** the competition profiler runs `llama-bench` + `lm-eval` against the raw GGUF only. Therefore (a) nothing in this document except the quantized GGUF artifact itself affects the leaderboard; (b) everything else in this document serves the demo, the judges' product evaluation, and the commercial system. Never trade (a) to improve (b).
4. **Budget discipline:** every resident byte and every thread is allocated in §5/§6. If an implementation needs more than its allocation, stop and update this TDD first — do not silently exceed caps.
5. **No network at runtime.** All model files, indexes, and assets ship in the bundle (§10). Build-time downloads happen only in the build environment (§11).
6. Paths are absolute under `/opt/tutor` at runtime and `./` (repo root) at build time. The repo layout mirrors §10.1.

---

## 1. Purpose and success criteria

The system is an offline AI mathematics tutor for West African exam preparation (WAEC/JAMB), deployed from a flash drive onto commodity laptops (CPU-only x86-64, 8 GB RAM), optionally serving up to 30 student phones over LAN from one laptop ("classroom server" mode).

**Success criteria:**
- **SC-1 (Leaderboard):** maximize `S = 0.50·S_acc + 0.30·S_tps + 0.20·S_eff` as computed by the competition `score.py` (exchange rates used for planning: +0.50 pts per accuracy point, +2.00 pts per tok/s, +2.86 pts per GB saved). Only the GGUF artifact moves this.
- **SC-2 (Demo):** a judge-visible session must show: photo of handwritten problem → correct worked solution with verified answer → rendered diagram → voice reply, with ≥ 4 concurrent sessions live and no visible degradation.
- **SC-3 (Product):** first token < 2.5 s for text at single-user load; audio round-trip (end of speech → first audio out) < 4 s; zero crashes across a 60-minute soak with 8 synthetic clients.
- **SC-4 (Envelope):** total system RSS ≤ 7.0 GiB on an 8 GiB machine at max supported concurrency; graceful degradation, never OOM of the core server.

---

## 2. Constraints and assumptions

| ID | Constraint | Consequence |
|----|-----------|-------------|
| C-1 | CPU-only x86-64, vendor unknown until 9–11 Aug | Baseline build targets AVX2 exactly; no AVX-512, no `-march=native` (DQ guard). Intel-only accelerants are conditional (§6.1, D4). |
| C-2 | 8 GiB RAM total, shared with OS/desktop | App envelope 7.0 GiB hard cap; per-service cgroup caps (§5.4). |
| C-3 | Decode is memory-bandwidth-bound on this class of hardware | Every speed lever is a bytes-per-token lever first (weights bits, KV bits, speculation). Arithmetic-only "optimizations" are ignored. |
| C-4 | No network at runtime; bundle ships on USB flash | Staging step copies bundle USB → local disk before serving (§10.3); mmap from USB is forbidden for resident models (first-touch page faults over USB destroy latency). |
| C-5 | Profiler = `llama-bench` + `lm-eval` on raw GGUF, mainline llama.cpp | Scored artifact must remain a mainline-loadable GGUF. Fork-only quant formats are leaderboard-ineligible by construction. |
| C-6 | Ubuntu 24.04 target OS; systemd available | Service management, cgroup caps, and watchdogs via systemd units (§10.4). |
| C-7 | Judges may be non-technical | All failure modes must degrade to a working text tutor; never to an error screen (§9 failure scenarios). |
| C-8 | Assume ≥ 4 physical cores; plan tables for 4/6/8 | Thread allocation table in §6.4. `[MEASURE: nproc; lscpu]` on the actual box, then apply the matching column. |

**Assumptions (falsifiable, tracked):** A-1: Qwen3.5-4B remains the bake-off winner (D1). A-2: pinned llama.cpp commit supports all flags listed in §6 `[VERIFY-AT-PIN]`. A-3: target box has ≥ 30 GB free disk for staging.

---

## 3. System overview

Hub-and-spoke: one strong reasoner is the hub; thin native sidecars convert modalities at the edges; deterministic renderers and a CAS verifier guarantee exactness where probabilistic generation is unacceptable; every behavioral variant is a LoRA adapter over the single resident weight set, never a second model.

```
                        ┌──────────────────────────────────────────────┐
                        │  Clients: local UI (browser), 30× phones LAN │
                        └──────────────┬───────────────────────────────┘
                                       │ HTTP/SSE/WS  :8080
                        ┌──────────────▼───────────────┐
                        │  GATEWAY (FastAPI, Python)   │  sessions, admission control,
                        │  + static UI + learning twin │  routing, tool loop, degradation
                        └──┬──────┬──────┬──────┬──────┘
            ┌──────────────┘      │      │      └──────────────────┐
            ▼                     ▼      ▼                         ▼
 ┌────────────────────┐  ┌──────────────────┐            ┌──────────────────────┐
 │ CORE-TEXT          │  │ AUDIO (sherpa-   │            │ TOOLS (in-gateway    │
 │ llama-server :8081 │  │ onnx)            │            │ subprocess pool)     │
 │ Qwen3.5-4B Q4_K_M  │  │ ASR ws :8084     │            │ • SymPy verify       │
 │ + LoRA adapters    │  │ TTS  ws :8085    │            │ • Renderer (mpl/SVG) │
 │ + spec decode      │  │ VAD (in-proc)    │            │ • ffmpeg frame sample│
 └────────────────────┘  └──────────────────┘            └──────────────────────┘
            │ on-demand (D3)                                       
            ▼                                              ┌──────────────────────┐
 ┌────────────────────┐  ┌──────────────────┐              │ RAG: FAISS index     │
 │ CORE-VISION        │  │ EMBED            │◄─────────────│ (mem-mapped, in      │
 │ llama-server :8082 │  │ llama-server     │   build-time │ gateway process)     │
 │ same GGUF + mmproj │  │ :8083 bge-small  │              └──────────────────────┘
 │ ephemeral, TTL 120s│  └──────────────────┘
 └────────────────────┘
 Parked (never resident): stable-diffusion.cpp batch job (§4.9)
```

**Why two core instances instead of one with `--mmproj` always loaded:** on current mainline, loading `--mmproj` sets the multimodal capability flag on **all** slots, which disables slot save/restore, context shift, and prompt-cache reuse even for text-only conversations (upstream issue #21133, open as of 2026-03). Those three mechanisms are load-bearing for the classroom server (§7.3, §8). Therefore text serving and vision serving are separate server processes over the **same weight file**; the OS page cache shares the read-only weight pages between them, so the marginal RAM of the vision instance is approximately mmproj weights + its own KV/compute buffers, not a second copy of the 4B weights. `[VERIFY-AT-PIN]`: if #21133 is fixed at the pinned commit, D3 may collapse to a single always-vision instance; keep the two-instance topology in config either way — it is strictly more robust.

---

## 4. Model inventory

Sizes are planning values; each has a `[MEASURE]` hook. "Resident" means loaded at boot and never evicted; "on-demand" means loaded on first request, evicted on TTL.

### 4.1 CORE — Qwen3.5-4B-Instruct, Q4_K_M GGUF  `[GATE: D1]`
- **Role:** all reasoning: tutoring dialogue, worked solutions, marking, tool-call emission, code emission for renderers.
- **Inputs:** text tokens (chat template via `--jinja`); vision embeddings only in the CORE-VISION instance.
- **Outputs:** text tokens; structured JSON when a grammar is attached (§7.4).
- **File:** `models/core/qwen3.5-4b-instruct-q4_k_m.gguf` — planning size **2.5 GiB** `[MEASURE: ls -l; sha256sum]`.
- **Variant selection (D1):** stock Q4_K_M vs own-imatrix Q4_K_M (imatrix calibrated on WAEC-domain corpus) vs Unsloth UD-Q4_K_XL. Winner = highest `score.py` output. Note: UD `_XL` files can contain f16 tensors incompatible with ik_llama.cpp (§6.1-B); if UD wins the leaderboard, demo engine variant B may still run a different quant — the scored file and the demo file need not be the same file, only the same model.
- **Context:** trained context ≥ 32k; we serve 4096/slot (classroom) and 8192 (single-user demo profile) — context is a RAM budget, not a capability target.
- **License:** Apache-2.0 (verify tag on the exact repo at download; record in `models/MANIFEST.json`).

### 4.2 MMPROJ — Qwen3.5-4B vision projector (Q8_0)
- **Role:** image → embedding sequence for CORE-VISION; also the video path (frames are images).
- **File:** `models/core/mmproj-qwen3.5-4b-q8_0.gguf` — planning size **0.5 GiB** `[MEASURE]`.
- **Input constraints (enforced at gateway):** JPEG/PNG/WebP; downscale longest side to ≤ 1280 px before submission; strip EXIF; reject > 8 MiB. Rationale: image token count scales with resolution in dynamic-resolution vision models; cap it or a single photo eats a slot's context. Use `--image-min-tokens` default from model metadata `[VERIFY-AT-PIN]`.
- **Loaded by:** CORE-VISION only (§3 rationale).

### 4.3 LoRA adapters (behavioral layer)
- **Role:** tutor persona, marking-scheme mode, future subjects. One resident base, N cheap behaviors.
- **Files:** `models/adapters/<name>.gguf`, planning size **50–200 MiB each**, Q8_0.
- **Mechanics:** all adapters are listed at server launch (`--lora-init-without-apply` + per-request activation). Per-request selection uses the completion-request `lora` field (list of `{id, scale}`); global fallback is `POST /lora-adapters`. `[VERIFY-AT-PIN]` — both API shapes exist upstream; confirm exact schema at the pinned commit and freeze it into the gateway client.
- **Rule:** fine-tunes always produce adapters, never merged weights (keeps hot-swap, keeps the scored GGUF untouched).

### 4.4 Speculative decoding assets  `[GATE: D2]`
Three mutually exclusive configurations; the gate picks one per engine variant:
- **D2-a (preferred, engine variant B only):** native MTP heads (ship inside the core checkpoint; ik_llama.cpp exposes MTP decode for Qwen3.5). Marginal RAM ≈ 0.
- **D2-b (mainline fallback):** draft-model speculation via `--spec-*` server flags with a tiny draft (`models/draft/qwen3.5-0.8b-q4_k_m.gguf`, planning **0.6 GiB**). Admission rule: adopt only if measured speedup ≥ 1.43× per ΔGiB spent, counting the draft's dual use as the hint-mode model (§7.6).
- **D2-c (zero-RAM fallback):** no speculation. Do not fabricate an n-gram path on mainline llama-server; self-speculative n-gram/suffix lives in engine variant B only.

### 4.5 ASR — Moonshine-tiny-en INT8 (sherpa-onnx zoo)
- **Role:** streaming English speech → text. **Files:** `models/asr/moonshine-tiny-en-int8/` — planning **< 100 MiB** `[MEASURE]`.
- **I/O:** 16 kHz mono PCM chunks in via WS; incremental transcript out; finalization on VAD endpoint (silence ≥ 0.5 s).
- **Escalation path (deferred, flag `asr.multilingual=true`):** Qwen3-ASR-0.6B for 52-language coverage — planning **0.7 GiB**; loading it displaces the vision instance headroom, so it is mutually exclusive with CORE-VISION at 8 GiB (§5.3 ladder).
### 4.6 VAD — Silero VAD (sherpa-onnx)
- `models/asr/silero-vad.onnx`, ~2 MiB. Runs inside the audio service; gates ASR compute and defines utterance endpoints.

### 4.7 TTS — Piper (default) + Kokoro-82M (optional premium)  `[GATE: D5]`
- **Piper:** `models/tts/piper/<voice>.onnx` + `.json`, **~75 MiB**, RTF ≈ 0.2–0.35 on modern x86 cores (3–5× realtime), 30+ languages available — the default for every session.
- **Kokoro-82M:** `models/tts/kokoro/`, **~330 MiB**, RTF ≈ 0.5–1.0 CPU, highest quality English; resident only in single-user demo profile, never in classroom profile.
- **I/O:** text (with SSML-lite markers for math verbalization, §7.7) → 24 kHz PCM stream over WS.

### 4.8 EMBED — bge-small-en-v1.5 Q8_0 GGUF
- **Role:** query-time embeddings for RAG; index built offline at bundle build.
- **File:** `models/embed/bge-small-en-v1.5-q8_0.gguf`, **~35 MiB**. Served by a dedicated `llama-server --embeddings` on :8083 with `--pooling cls`, `-c 512`, `-np 2`, 1 thread. Rationale for GGUF-over-ONNX: keeps the runtime count at exactly two (llama.cpp family + sherpa-onnx) — no third inference stack for one tiny model.

### 4.9 Parked — stable-diffusion.cpp
- Never resident. If the image-generation nice-to-have is activated post-competition, it runs as a batch job through the same process-manager with `swap:true` semantics (§7.8). Not in the competition bundle.

### 4.10 Non-model executables that behave like models
- **SymPy verifier** (Python subprocess pool): answer-equivalence checking; deterministic; §7.5.
- **Renderer** (Python subprocess pool): Matplotlib/TikZ→SVG from model-emitted code; sandboxed; §7.5.
- **ffmpeg**: video → ≤ 8 frames at ≤ 1 fps for the vision path; static binary in bundle.

---

## 5. Memory architecture

### 5.1 Global budget (8192 MiB machine)

| Pool | Cap (MiB) | Enforced by |
|---|---|---|
| OS + desktop reserve | 1200 | (unmanaged; measured baseline `[MEASURE: free -m` on idle box`]` |
| CORE-TEXT (weights mmap + KV + compute buffers) | 4300 | `MemoryMax` on `tutor-core.service` |
| CORE-VISION (marginal: mmproj + KV + buffers; weights shared via page cache) | 1100 | `MemoryMax` on transient scope |
| AUDIO (sherpa ASR+VAD+TTS) | 450 | `MemoryMax` on `tutor-audio.service` |
| EMBED server | 150 | `MemoryMax` on `tutor-embed.service` |
| GATEWAY + UI + FAISS (mmap) + twin store | 600 | `MemoryMax` on `tutor-gw.service` |
| Tool subprocess pool (SymPy/renderer, peak) | 300 | rlimits per subprocess (§7.5) |
| Slack (page cache churn, spikes) | ~92+ | earlyoom threshold |
| **App envelope total** | **≤ 7000** | SC-4 |

Notes: (1) CORE-VISION's cap is *marginal* because the 2.5 GiB weight file is the same inode as CORE-TEXT's — read-only mmap'd pages are shared in page cache; cgroup accounting attributes shared pages to first-toucher, so set CORE-TEXT's cap high enough to own them. (2) When CORE-VISION is not running, its 1100 MiB returns to slack — this is the "vision headroom" the degradation ladder spends (§5.3).

### 5.2 KV cache mathematics (worked example — re-derive from actual metadata)

Per-token KV bytes = `2 (K and V) × n_layer × n_kv_head × head_dim × bytes_per_element`.
Extract the real values: `[MEASURE: python gguf-py/scripts/gguf_dump.py models/core/*.gguf | grep -E "block_count|head_count_kv|key_length"]`.

Worked example with representative Qwen-family 4B values (n_layer=36, n_kv_head=8, head_dim=128):
- elements/token = 2×36×8×128 = 73,728
- f16 (2 B/el): 144 KiB/token → 4096-token slot = **576 MiB**
- q8_0 (~1.0625 B/el): ~76.5 KiB/token → 4096-token slot = **306 MiB**
- q5_1 (~0.75 B/el): ~54 KiB/token → 4096-token slot = **216 MiB**

**Slot budget table (q8_0, planning values — refresh after `[MEASURE]`):**

| Profile | `-c` total | `-np` | ctx/slot | KV total | Fits CORE-TEXT cap? |
|---|---|---|---|---|---|
| Classroom-8 | 32768 | 8 | 4096 | ~2.4 GiB | Yes (2.5 weights + 2.4 KV + ~0.6 buffers ≈ 5.5 → **exceeds 4300**; see below) |
| Classroom-6 | 24576 | 6 | 4096 | ~1.8 GiB | Yes: 2.5+1.8+0.6 ≈ 4.9 → still tight |
| Classroom-6-short | 12288 | 6 | 2048 | ~0.9 GiB | Yes: ≈ 4.0 ✓ **default classroom profile** |
| Solo-demo | 8192 | 2 | 4096 | ~0.6 GiB | Yes: ≈ 3.7 ✓ + room for Kokoro |

The table encodes the central tension: **slots × context is the commodity RAM buys.** Default = Classroom-6-short; 30 phones share 6 active slots via suspend/resume (§8). If measurement shows head_dim/kv_heads smaller than the example, promote to Classroom-8. The compute-buffer term (~0.6 GiB at `-b 2048/-ub 512`) shrinks if `-ub` is lowered — part of the batch sweep (§6.3).

### 5.3 Degradation ladder (runtime, automatic)

| Level | Trigger (gateway-evaluated) | Action |
|---|---|---|
| L0 normal | free envelope ≥ 1.2 GiB | all features on |
| L1 | free < 1.2 GiB OR vision requested while audio multilingual loaded | deny new CORE-VISION spawn; queue vision jobs |
| L2 | free < 0.8 GiB | new sessions get ctx 2048; TTS switches Kokoro→Piper if applicable |
| L3 | free < 0.5 GiB OR earlyoom warning | pause TTS synthesis; suspend idle slots to disk (§8.3); refuse new sessions with friendly message |
| L4 | core server RSS > cap − 100 MiB | emergency: drop to `-np` effective 4 via admission; never kill core |

"Free envelope" = `MemAvailable` from `/proc/meminfo` minus a 300 MiB floor, polled every 2 s by the gateway.

### 5.4 OS-level guards (installed by bundle, §10.4)
- **cgroups:** every service unit sets `MemoryMax` (hard) and `MemoryHigh` (= Max − 10%) so reclaim pressure precedes the kill.
- **earlyoom:** `-m 4 -s 100 --avoid '(^|/)llama-server-core($|\s)' --prefer '(renderer|sympy)'` — sacrifice tool subprocesses first, never the core.
- **zram:** 2 GiB lz4 swap-on-zram, `vm.swappiness=80` for anonymous pages only. Rationale: on an 8 GiB box, compressed swap converts ~1 GiB of cold anonymous memory into ~400 MiB physical at small CPU cost; it is a shock absorber, not budget — planning numbers above assume zram absorbs spikes, not steady state.
- **mlock policy:** CORE-TEXT weights are `--mlock`ed **only after** staging to local disk (C-4) and only in solo-demo profile; in classroom profile rely on page cache (mlock of 2.5 GiB + strict cgroup caps risks reclaim pathologies). `[GATE: D9 — flip if soak test shows major-fault jitter]`.

---

## 6. Inference engine specification

### 6.1 Engine variants (build matrix)

| Variant | Base | Role | Adoption rule |
|---|---|---|---|
| **A (guaranteed)** | mainline llama.cpp, pinned commit `LLAMA_PIN=<sha>` (set at T1, record in `versions.lock`) | scored artifact tooling + default demo serving | always built, always shipped |
| **B (accelerant)** | ik_llama.cpp, pinned | demo serving if it loads Qwen3.5-4B and beats A by ≥ 10% decode TPS on target box; unlocks D2-a (MTP) and self-spec n-gram/suffix | gated: arch support check + bench ≥ 1.10× A |
| **C (Intel-conditional)** | mainline + OpenVINO backend (preview) | demo serving only if target CPU is Intel AND model loads AND beats best-of(A,B) | gated: `lscpu` vendor == GenuineIntel + bench win; preview status means C never ships as the only binary |

**Build commands (variant A):**
```bash
cmake -B build \
  -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF -DGGML_FMA=ON -DGGML_F16C=ON \
  -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target llama-server llama-bench llama-quantize llama-cli
```
Rationale: `GGML_NATIVE=OFF` + explicit AVX2 = the DQ guard (C-1): the binary must run on any x86-64-v3 machine, and must not embed AVX-512 paths that trap on AMD/older-Intel judges' hardware. Static build (`BUILD_SHARED_LIBS=OFF`) removes .so path issues on the target machine. Variant B: same flags against the ik_llama.cpp tree; additionally test `-rtr` (runtime row-interleave repack) at serve time — it repacks in RAM, so it costs load latency, not file changes. Variant C: follow `docs/backend/OPENVINO.md` in-tree; pin the OpenVINO runtime version it names; bundle its shared libs under `bin/ov/` with `LD_LIBRARY_PATH` set only for that binary.

### 6.2 CORE-TEXT server — full invocation (profile: Classroom-6-short)

```bash
llama-server \
  -m /opt/tutor/models/core/qwen3.5-4b-instruct-q4_k_m.gguf \
  --alias core \
  --host 127.0.0.1 --port 8081 \
  -c 12288 --parallel 6 --kv-unified \
  --cont-batching \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --flash-attn on \
  -b 2048 -ub 512 \
  --threads {T_gen} --threads-batch {T_batch} --threads-http 2 \
  --cache-reuse 256 \
  --cache-ram 512 \
  --slot-save-path /opt/tutor/data/kv-slots/ \
  --context-shift \
  --defrag-thold 0.10 \
  --lora-init-without-apply \
  --lora /opt/tutor/models/adapters/tutor-persona.gguf \
  --lora /opt/tutor/models/adapters/marking-mode.gguf \
  --jinja \
  --metrics --slots --props --no-webui \
  --api-key "$(cat /opt/tutor/data/api.key)" \
  --seed -1 \
  --log-file /opt/tutor/logs/core.jsonl
```

**Flag-by-flag rationale and nuances (the knobs):**

| Flag | Value | Why / nuance |
|---|---|---|
| `-c` / `--parallel` | 12288 / 6 | `-c` is the TOTAL context budget divided across slots (→ 2048/slot). This is the primary RAM knob (§5.2). `--parallel` default is auto (-1); always set explicitly — auto-sizing fights the cgroup cap. |
| `--kv-unified` | on | single shared KV buffer across slots → per-slot ctx becomes a soft bound; a long solo session can borrow unused slot budget. `[VERIFY-AT-PIN]` interaction with `--cache-idle-slots` (below). |
| `--cache-type-k/v q8_0` | q8_0 | halves KV vs f16 with no measurable quality loss at this size; the D6 ladder (f16→q8_0→q5_1→tq3_0) is swept in bench week; q8_0 is the shipping default. V-cache quantization historically requires flash attention — hence next row. |
| `--flash-attn on` | on (not auto) | default is `auto`; force `on` so bench numbers are stable across environments; reduces attention working memory O(N²)→O(N) and is prerequisite-coupled to quantized V. If the pinned build refuses (`unsupported`), fall back to `auto` and record it. |
| `-b` / `-ub` | 2048 / 512 | logical/physical batch; governs prefill blocking and compute-buffer size. Sweep `-ub ∈ {128,256,512}` on the target box (bench T13): lower `-ub` shrinks buffers (§5.2) at some prefill cost — on 8 GiB, 256 may be the right trade. |
| `--threads` / `--threads-batch` | per §6.4 | decode threads vs prefill threads. Decode is bandwidth-bound: more threads than physical cores HURTS. Prefill is compute-bound: `threads-batch` may exceed `threads`. |
| `--cache-reuse 256` | 256 | enables chunk-level KV reuse via shifting for shared prompt chunks ≥ 256 tokens — this is what makes the RAG prompt layout (§7.3) cheap. Requires prompts engineered stable-prefix-first. |
| `--cache-ram 512` | 512 MiB | resident prompt-cache pool beyond live slots; keeps warmed prefixes (system prompt + syllabus header) across slot churn. Budgeted inside CORE-TEXT's cap. `--cache-idle-slots` stays default-on (requires cache-ram). |
| `--slot-save-path` | data/kv-slots/ | enables `/slots/{id}?action=save|restore` — the suspend/resume mechanism for 30-students-on-6-slots (§8.3) and crash-warm-restart. Disk cost ≈ slot KV size per saved session; cap directory at 4 GiB, LRU-evict (gateway job). |
| `--context-shift` | on | default is now DISABLED upstream; we enable it so infinite tutoring dialogs never hard-stop. Nuance: with q8_0 KV, context shift may force partial reprocessing on some builds `[VERIFY-AT-PIN]`; acceptable. |
| `--defrag-thold 0.10` | 0.10 | KV fragmentation defrag trigger; with unified KV + churny classroom slots, fragmentation is real; 0.10 is conservative. |
| `--lora-init-without-apply` + `--lora ×N` | listed | all adapters loaded but inactive at start; activation per request (§7.4). Ensures zero adapter cost on plain requests. |
| `--jinja` | on | use the model's own chat template (tool-call tokens included). Never hand-roll the template. |
| `--metrics --slots --props` | on | Prometheus metrics + per-slot state + server props — the gateway's health/telemetry surface (§12). |
| `--no-webui`, `--api-key` | set | classroom = LAN-exposed via gateway only; core binds loopback; key defends against curious students port-scanning the laptop. |
| `--seed -1` | -1 | random per request; verifier/marking requests override seed per-request for reproducibility (§6.5). |
| NOT set: `--mlock` | — | D9 (§5.4). NOT set: `--numa` — single-socket assumption; if `lscpu` shows 2 nodes, add `--numa distribute`. NOT set: `--swa-full` — Qwen3.5 is not SWA; irrelevant. |

**Speculation flags (only when D2-b active):** append
`--model-draft /opt/tutor/models/draft/qwen3.5-0.8b-q4_k_m.gguf --draft-max 8 --draft-min 1 --draft-p-min 0.75 --threads-draft {T_draft}` `[VERIFY-AT-PIN: exact spec flag spelling at pinned commit]`. Nuance: speculation multiplies *verify* batch work — re-run the `-ub` sweep with speculation on; optimal `-ub` usually rises.

### 6.3 CORE-VISION server (ephemeral, spawned by gateway)

Same binary, same GGUF, plus: `--port 8082 --mmproj /opt/tutor/models/core/mmproj-qwen3.5-4b-q8_0.gguf -c 8192 --parallel 2 --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on -b 1024 -ub 256 --threads {T_vis}` and WITHOUT: `--cache-reuse`, `--slot-save-path`, `--context-shift` (all blocked under mmproj per #21133 — don't request what will assert). Lifecycle: spawn on first vision request (cold spawn budget ≤ 6 s from page-cache-warm weights `[MEASURE]`), TTL-kill after 120 s idle, hard-denied at ladder ≥ L1. Video requests: gateway runs `ffmpeg -i in.mp4 -vf fps=1,scale='min(1280,iw)':-2 -frames:v 8 f_%02d.jpg` and submits frames as a multi-image message.

### 6.4 Thread allocation table (physical cores → assignments)

| Physical cores | CORE `--threads` | CORE `--threads-batch` | vision `T_vis` | sherpa (ASR/TTS) | gateway+tools | Notes |
|---|---|---|---|---|---|---|
| 4 | 3 | 4 | 2 | 1 each | share leftovers | vision and audio contend; ladder L1 earlier |
| 6 | 4 | 6 | 3 | 1 each | 1 | default planning row |
| 8 | 6 | 8 | 4 | 1–2 each | 1–2 | |

Rules: never count SMT siblings for `--threads` (bandwidth-bound decode gains nothing, loses cache); pin services with `CPUAffinity=` in units so audio never starves mid-utterance (audio glitches are more judge-visible than 5% TPS); `--threads-http 2` always. `[MEASURE: llama-bench -t sweep on target]`.

### 6.5 Sampling profiles (gateway-attached per request)

| Mode | temp | top_p | top_k | min_p | repeat_penalty | seed | grammar |
|---|---|---|---|---|---|---|---|
| tutor-dialogue | 0.7 | 0.95 | 40 | 0.05 | 1.05 | -1 | none |
| worked-solution | 0.3 | 0.9 | 40 | 0.05 | 1.05 | -1 | none |
| marking / verifier-retry | 0.0 (greedy) | 1.0 | 1 | 0 | 1.0 | 4242 | JSON schema (§7.4) |
| tool-call emission | 0.0 | 1.0 | 1 | 0 | 1.0 | 4242 | JSON schema |
| hint-mode (draft model, D2-b) | 0.8 | 0.95 | 40 | 0.05 | 1.1 | -1 | none |

Greedy + fixed seed for anything scored or verified: reproducibility is a feature (bug reports become replayable).

### 6.6 Audio engine (sherpa-onnx) — build and serve

Build once, static: `cmake -B build -DSHERPA_ONNX_ENABLE_TTS=ON -DSHERPA_ONNX_ENABLE_BINARY=ON -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF` (CPU provider only). Serve two websocket endpoints from one service:
- **ASR** :8084 — streaming Moonshine INT8 + Silero VAD; config: `chunk 0.2s, endpoint rule: trailing silence 0.5s`, `num_threads=1`, decode `greedy_search`.
- **TTS** :8085 — Piper voice default; `num_threads=1`; sentence-level streaming: gateway splits model output on sentence boundaries and pipelines synthesis so first audio ≤ 1 s after first sentence completes.
Nuances: ONNX Runtime intra-op threads are the only real knob on CPU; >1 thread helps Kokoro, not Piper `[MEASURE: RTF at threads∈{1,2}]`. Both model dirs are declared in one `audio.yaml` so voices/languages are data changes, not code changes.

### 6.7 Embedding server

`llama-server -m models/embed/bge-small-en-v1.5-q8_0.gguf --embeddings --pooling cls -c 512 -np 2 --threads 1 --port 8083 --no-webui --api-key ...`. Note `--pooling cls` (BGE family uses CLS pooling; mean-pooling silently degrades retrieval). Index side: FAISS `IndexFlatIP` over normalized vectors (corpus small enough that flat beats IVF complexity), mmap'd read-only in the gateway.

---

## 7. Gateway and orchestration

### 7.1 Process model
FastAPI app (uvicorn, 1 worker, async) owning: session table, admission control (§8), degradation ladder (§5.3), the CORE-VISION process manager (D7 resolved: gateway-managed subprocess via `systemd-run --scope -p MemoryMax=1100M`, TTL reaper task; llama-swap and llama-server router mode remain documented alternatives — adopt only if the process manager exceeds 200 LoC or three bugs), tool subprocess pools, WS bridging to audio services, static UI serving.

### 7.2 Frozen API (OpenAPI 3.1 skeleton in Appendix D)
`POST /v1/tutor/chat` (SSE) · `POST /v1/tutor/vision` (multipart) · `WS /v1/audio/stream` (bidirectional: PCM in, transcript + PCM out) · `POST /v1/tutor/verify` · `POST /v1/tutor/render` · `POST /v1/session/{id}/suspend|resume` · `GET /v1/health` · `GET /v1/metrics`. Contract rule: additive changes only after 2026-08-01.

### 7.3 Prompt layout (cache-reuse-engineered)
Order every prompt: `[static system+persona] → [semi-static: syllabus header, marking rubric] → [RAG chunks, stable-sorted by doc id] → [session summary] → [turn history] → [user turn]`. Rationale: `--cache-reuse 256` reuses shared chunks by KV shifting; stable ordering maximizes shared-prefix length across requests and sessions. RAG chunks are stable-sorted (not relevance-sorted) within the context block; relevance affects selection, not order — measured prefill savings is the point `[MEASURE: cache_hits via /metrics]`.

### 7.4 Tool loop
Model emits tool calls under JSON-schema grammar (`response_format: json_schema` per request). Tools: `verify_answer(expr, expected)`, `render_diagram(kind, code)`, `lookup(query)` (RAG), `set_mode(adapter)`. Loop: max 3 tool rounds per turn; each round re-enters CORE with tool results appended; adapter switching = per-request `lora` field change (4.3), which costs nothing but cache — an adapter switch invalidates reuse for the affected prefix, so persona/marking adapters attach at the *semi-static* layer boundary, keeping the static layer shared.

### 7.5 Deterministic tools (sandboxed)
SymPy verifier and renderer run in a prefork pool (2 workers each, warm imports): `python -I -S`, `resource.setrlimit`: AS 256 MiB, CPU 5 s, NOFILE 32; no network (`unshare -rn` wrapper where available, else socketless audit); renderer whitelist: matplotlib.Agg, numpy, sympy.plotting; output = SVG string ≤ 512 KiB. Verifier protocol: extract final answer (regex + `\boxed{}` conventions) → `sympy.simplify(a - b) == 0` with timeout → on mismatch, ONE retry with the failure injected as a hint at temp 0.0 → on second failure, respond honestly with "let's check this one together" framing (C-7: never present unverified as verified).

### 7.6 Hint mode (D2-b only)
If the draft model is resident, `POST /v1/tutor/chat?mode=hint` routes to it directly (own tiny server on :8086, `-c 2048 -np 2`) for instant Socratic nudges; full solutions always route to CORE. This is what makes the draft's ΔRAM admissible under the 1.43× rule.

### 7.7 Math-to-speech
Before TTS, a text normalizer converts LaTeX/Unicode math to spoken English ("x squared plus three x over two"), sentence-splits, and tags language per sentence for voice routing. Ship as a pure-Python module with a golden test set of 60 expressions (T9 acceptance).

### 7.8 Batch lane (parked)
Process-manager supports `class=batch` jobs (nice 19, `MemoryMax` from vision headroom, only at ladder L0). stable-diffusion.cpp registers here post-competition; nothing else uses it now.

---

## 8. Session and concurrency model (30 phones, 6 slots)

### 8.1 Definitions
A **session** = one student's persistent tutoring state: learning-twin JSON + (optionally) a saved KV snapshot. A **slot** = a live decode lane in CORE-TEXT. Sessions ≫ slots by design.

### 8.2 Admission control (gateway)
New request for session S: if S holds a slot → enqueue on it. Else if a free slot exists → bind. Else if an idle-bound slot exists (no request in flight, idle > 20 s) → suspend that session (8.3), bind S. Else → queue with position feedback to the client ("2 students ahead"). Fairness: per-session token budget of 1200 output tokens per turn (tutor answers are naturally shorter); round-robin across queued sessions.

### 8.3 Suspend/resume
Suspend = `POST :8081/slots/{id}?action=save` → file `data/kv-slots/{session}.bin` + twin flush. Resume = `action=restore` (prefill cost ≈ 0) — this converts the 6-slot server into a 30-student server with a suspend/resume cost of one disk write/read (~300 MiB at Classroom-6-short ctx 2048 ≈ 150 MiB/slot; NVMe/SATA both fine, USB forbidden per C-4). Restore-miss (evicted or corrupt snapshot) falls back to twin-summary re-prefill: system+syllabus prefix comes from prompt cache (`--cache-ram`), so the miss costs one summary prefill, not a cold start. LRU cap on the snapshot dir: 4 GiB (gateway reaper).

### 8.4 Learning twin (product state)
`data/twins/{student}.json`: mastery vector over curriculum-graph nodes, error taxonomy counts, pace stats, last-N summaries. All writes atomic (`write tmp → fsync → rename`). The twin is the source of the session summary layer in §7.3 — meaning suspend/resume and personalization ride the same artifact.

---

## 9. Scenarios — normal and failure paths (exhaustive)

**S1 Text Q&A (baseline).** UI → gateway → CORE (tutor-dialogue profile) → SSE stream. Verify loop only if the turn contains a final numeric/symbolic answer.

**S2 Photo of handwritten problem.** UI multipart → gateway image guard (4.2) → ensure CORE-VISION (spawn if needed; user sees "reading your work…" state) → vision completion returns problem transcription + analysis → gateway hands transcription to CORE-TEXT session (so the expensive instance stays stateless and TTL-killable) → normal S1 flow. Failure: spawn denied (ladder ≥ L1) → honest fallback: "type the problem for now" + queue ticket.

**S3 Voice question.** Mic PCM → WS → VAD gates ASR → finalized transcript echoed to UI (student confirms/edits — trust checkpoint) → S1 flow → sentence-split → TTS stream. Failure: ASR confidence < threshold → ask to repeat, never guess into the solution path.

**S4 Video clip.** Guard ≤ 30 s, ≤ 50 MiB → ffmpeg frames (6.3) → S2 path with multi-image message. Classroom profile: video queued as batch-class job, never inline.

**S5 Diagram request.** CORE emits `render_diagram` code → sandbox renders SVG → inline in chat + downloadable. Failure: render error/timeout → one repair round with stderr as tool result → else text-only description (never a broken image).

**S6 Marking mode.** Marking adapter + rubric RAG + greedy profile + JSON schema {per-step marks, error tags, total}. Twin updated with error tags.

**S7 Exam simulation.** Timed paper from generator bank → S6 marking per question → percentile lookup against cohort table → report card (also the parent-report artifact).

**S8 Multilingual voice.** Language toggle → TTS voice map (Piper voice per language; missing voice → text-only reply with notice); ASR stays English until D-multilingual flips (4.5 exclusivity rule with vision — enforced by ladder L1).

**S9 Suspend/resume at scale.** Covered by 8.2/8.3; soak test T15 replays 30 synthetic students with Zipf arrival.

**S10 Cold start / staging.** First boot from USB: integrity check (`sha256 manifest`) → copy bundle → disk (progress UI) → warm page cache (`vmtouch -t` core GGUF, or `dd > /dev/null`) → services up → self-test (one canned S1+S5 round) → "ready" screen. Target ≤ 4 min on USB-3 `[MEASURE]`.

**S11 Crash/restart of core.** systemd `Restart=on-failure` (2 s backoff); gateway detects via health poll, replays nothing (idempotent SSE turns), sessions resume from snapshots/twins. Judge-visible gap target < 10 s.

**S12 Resource attacks & edge inputs.** Oversized image (reject 413), 40-minute audio stream (VAD hard cap 90 s/utterance), prompt bomb (input cap 4 KiB text/turn), renderer infinite loop (rlimit kills, S5 fallback), USB yanked post-staging (irrelevant — running from disk), disk full (snapshot writes fail → suspend disabled → ladder L3 messaging), clock skew (all timers monotonic).

---

## 10. Storage, deployment, services

### 10.1 Layout (bundle = repo `dist/`, installed at `/opt/tutor`)
```
/opt/tutor/
  bin/            llama-server-core (A), llama-server-ik (B, opt), ov/ (C, opt),
                  sherpa-asr, sherpa-tts, ffmpeg, vmtouch, earlyoom
  models/         core/ (gguf + mmproj)  adapters/  draft/ (opt)
                  asr/  tts/  embed/     MANIFEST.json (path,size,sha256,license)
  index/          faiss.bin  chunks.sqlite  cohorts.sqlite  curriculum.json
  gw/             app/ (FastAPI)  ui/ (static)  requirements.lock  venv/
  data/           twins/  kv-slots/  logs/  api.key   (created at install, mode 0700)
  units/          *.service, *.scope templates, earlyoom.conf, zram.conf
  install.sh  stage.sh  selftest.sh  versions.lock
```

### 10.2 Manifest and integrity
`MANIFEST.json` lists every binary/model with sha256 + license id. `stage.sh` verifies all hashes before copy and after copy (bitrot on cheap flash is real). Any mismatch → refuse to start, name the file.

### 10.3 Staging rule
Never serve models from USB (C-4). `stage.sh`: verify → rsync to `/opt/tutor` → re-verify → `vmtouch -t models/core/*.gguf` → enable units.

### 10.4 systemd units (all with `Slice=tutor.slice`)
- `tutor-core.service`: ExecStart §6.2 · `MemoryMax=4300M MemoryHigh=3900M CPUWeight=800 Restart=on-failure RestartSec=2 WatchdogSec=30` (llama-server lacks sd_notify — implement watchdog as gateway-side health probe + `systemctl restart` fallback, not WatchdogSec) `[VERIFY-AT-PIN]`.
- `tutor-audio.service`: `MemoryMax=450M CPUWeight=300 CPUAffinity={audio core}` — audio dropouts are judge-visible; protect its core.
- `tutor-embed.service`: `MemoryMax=150M CPUWeight=100`.
- `tutor-gw.service`: `MemoryMax=600M CPUWeight=400 After=tutor-core tutor-audio tutor-embed`.
- CORE-VISION: transient scope via `systemd-run --scope -p MemoryMax=1100M -p CPUWeight=500` from the gateway.
- `earlyoom.service` (§5.4), zram via `systemd-zram-setup@zram0` (2 GiB, lz4).

### 10.5 Profiles
`PROFILE=classroom` (default: Classroom-6-short, Piper, no Kokoro) · `PROFILE=solo-demo` (Solo-demo table row, Kokoro resident, `--mlock` per D9). One env file `etc/profile.env` switches everything; both profiles smoke-tested in CI (T16).

---

## 11. Build and packaging (build machine ≠ target machine)

1. `build.sh` compiles variants A (+B, +C if enabled) with pinned SHAs from `versions.lock`; refuses to build if `git describe` ≠ lock.
2. `fetch_models.sh` downloads model files by exact revision hash into `models/`, writes MANIFEST (build-time network only).
3. Quantization lane (leaderboard artifact): `make_quants.sh` produces stock/imatrix/UD candidates; `bench_matrix.sh` runs `llama-bench` (fixed: `-p 512 -n 128 -t {T}` ×5, report median±sd) + `lm-eval` task set + RSS capture (`/proc/{pid}/smaps_rollup` VmRSS peak) → `score.py` → `bench/results.csv`. D1 = argmax row. The scored GGUF is copied VERBATIM into the submission folder; nothing at serve time may rewrite it.
4. `package.sh` assembles `dist/`, runs `selftest.sh` inside a clean Ubuntu 24.04 container with `--network none` and 8 GiB memory limit — the clean-room rehearsal (T16 acceptance).

---

## 12. Observability (all local)

- Structured JSONL logs per service (`logs/*.jsonl`), rotated at 50 MiB ×3.
- Gateway scrapes `:8081/metrics`, `:8083/metrics` + its own counters every 10 s into `data/metrics.sqlite` (llama.cpp exposes Prometheus-format metrics incl. prompt/decode tok/s and cache hits).
- Derived panels (simple HTML page `/v1/health/ui`): decode TPS, TTFT p50/p95, cache-hit ratio, RSS per service vs cap, ladder level, slots busy/saved, audio RTF.
- Product telemetry (efficacy instrumentation): diagnostic scores pre/post, per-node mastery deltas, session minutes — the data that becomes the "+X% improvement" number. Local-only, exportable by explicit teacher action.

## 13. Security and safety

Gateway is the only LAN-exposed surface (:8080); core/audio/embed bind loopback with API key. Input caps per S12. Renderer/verifier sandboxing per §7.5. RAG/teacher-injected content is data, not instructions: retrieved chunks are wrapped in delimiters and the system prompt states they are reference material — prompt-injection posture documented, not assumed solved. Student data stays on device; twin export requires teacher PIN. Licenses: every shipped artifact's license recorded in MANIFEST; Apache-2.0/MIT-only policy for redistribution.

---

## 14. Decision register (open gates)

| ID | Decision | Default | Alternative | Trigger to flip | Owner/date |
|---|---|---|---|---|---|
| D1 | Core quant variant | own-imatrix Q4_K_M | stock / UD-Q4_K_XL | `score.py` argmax from bench matrix | bake-off close-out |
| D2 | Speculation | c (none) on variant A; a (MTP) on variant B | b (draft model) | B loads Qwen3.5 & MTP works → a; else draft clears 1.43×/ΔGiB → b | 27 Jul gate |
| D3 | Vision topology | two instances (text + ephemeral vision) | single always-vision instance | #21133 confirmed fixed at pin AND headroom ≥ 1.1 GiB steady | at pin |
| D4 | Demo engine binary | A | B if ≥1.10× A; C if Intel AND beats best | on-target bench 9–11 Aug | hardware day |
| D5 | Premium TTS | Piper only | +Kokoro in solo-demo | solo-demo RSS ≤ 6.5 GiB with Kokoro resident | demo rehearsal |
| D6 | KV cache type | q8_0 | q5_1 / tq3_0 | ladder sweep shows no eval regression AND slots gained | KV ladder day |
| D7 | Vision process mgmt | gateway subprocess mgr | llama-swap / router mode | mgr > 200 LoC or 3 bugs | anytime |
| D8 | Embedding model | bge-small-en-v1.5 Q8_0 | multilingual-e5-small | multilingual RAG corpus lands | post-comp |
| D9 | mlock core weights | off (classroom) / on (solo-demo) | flip | soak shows major-fault jitter > 50 ms p95 | soak test |

## 15. Implementation plan (Claude Code task list — strict order)

Each task ends with its acceptance check green and results appended to `bench/results.csv` or `test/report.md`. Never mark a `[MEASURE]` as done with a planning value.

- **T1** Pin & build variant A; record `versions.lock`. ✓ `llama-server --version` matches lock; binary runs on a non-AVX512 container.
- **T2** `fetch_models.sh` + MANIFEST for core, mmproj, asr, tts, embed. ✓ hashes verify twice.
- **T3** Repo skeleton per §10.1 + `install.sh`/`stage.sh`. ✓ stage from a real USB onto a clean VM; integrity paths exercised (corrupt one byte → refusal names the file).
- **T4** Bring up CORE-TEXT with §6.2 flags; smoke chat via curl. ✓ `/props` reflects every flag; `/metrics` scrapes.
- **T5** KV math refresh from gguf metadata; regenerate §5.2 table; pick profile row. ✓ table committed with measured values.
- **T6** Gateway skeleton: sessions, SSE chat passthrough, sampling profiles, health poll. ✓ S1 end-to-end.
- **T7** Prompt layout + `--cache-reuse` verification. ✓ cache-hit tokens > 60% on repeated syllabus queries (metrics evidence).
- **T8** Tool loop + SymPy verifier + renderer sandbox. ✓ 60-expression golden set: 100% verifier correctness, 0 sandbox escapes (rlimit tests).
- **T9** Audio service: ASR ws, VAD endpointing, TTS ws, math-to-speech normalizer. ✓ S3 round-trip < 4 s on dev box; 60-expression speech goldens pass review.
- **T10** CORE-VISION manager: spawn/TTL/deny; S2 flow. ✓ spawn ≤ 6 s warm; ladder L1 denial path returns friendly fallback.
- **T11** Embedding server + FAISS build + RAG retrieve. ✓ top-3 recall ≥ 90% on 50 seeded queries.
- **T12** Suspend/resume: slot save/restore + twin summaries + LRU reaper. ✓ 30 synthetic students on 6 slots, zero cold starts after warmup (log evidence).
- **T13** Bench week scripts: `bench_matrix.sh`, `-ub` sweep, thread sweep, KV ladder, spec gate. ✓ CSV rows for every cell; D1/D2/D6 decided from data.
- **T14** Degradation ladder + earlyoom + zram + cgroup caps live. ✓ chaos test: balloon 1.5 GiB → ladder walks L1→L3 → release → walks back; core never killed.
- **T15** Soak: 60 min, 8 clients mixed S1/S2/S3/S5. ✓ SC-3, SC-4 numbers recorded.
- **T16** Clean-room: `package.sh` + container selftest `--network none`, both profiles. ✓ green.
- **T17** (conditional) Variants B/C builds + on-target bench harness for hardware day. ✓ one-command compare report.
- **T18** Demo assets: seeded twins, canned S2 photo, S7 exam, judge script hooks. ✓ full SC-2 rehearsal recorded.

## 16. Risk register (top)

| Risk | L×I | Mitigation |
|---|---|---|
| #21133 unfixed → vision instance jitter under load | M×M | two-instance topology is the mitigation; TTL + L1 denial bound the cost |
| Draft/MTP path fails on 27 Jul | M×L | D2-c ships fine; speculation is upside, not baseline |
| Target box has 4 cores | M×M | 4-core column §6.4; Classroom-6-short still fits; demo narrative emphasizes concurrency not raw TPS |
| USB bitrot / slow flash | M×H | dual hash verify + staging + spare drive in kit |
| Qwen3.5 mmproj under-documented edge (huge handwriting photos) | M×M | image guard caps tokens; S2 fallback to typed input |
| RSS creep (Python gateway) | M×M | `MemoryMax=600M` + soak T15 + object-count logging |
| Preview backend C crashes on stage | L×H | C never the only binary; D4 requires bench win on the actual box |

---

## Appendix A — OpenAPI 3.1 skeleton (freeze target)

```yaml
openapi: 3.1.0
info: {title: Tutor Gateway, version: 1.0.0}
paths:
  /v1/tutor/chat:      {post: {summary: SSE tutoring turn, requestBody: {content: {application/json: {schema: {$ref: '#/components/schemas/ChatTurn'}}}}}}
  /v1/tutor/vision:    {post: {summary: image/video problem intake (multipart)}}
  /v1/tutor/verify:    {post: {summary: SymPy equivalence check}}
  /v1/tutor/render:    {post: {summary: code→SVG render}}
  /v1/session/{id}/suspend: {post: {}}
  /v1/session/{id}/resume:  {post: {}}
  /v1/health: {get: {}}
components:
  schemas:
    ChatTurn: {type: object, required: [session_id, text], properties: {
      session_id: {type: string}, text: {type: string},
      mode: {enum: [dialogue, solution, marking, hint]},
      lang: {type: string, default: en}}}
```

## Appendix B — Documented alternatives (do not build unless D7 flips)

**llama-swap group config sketch:** resident group `{core-text, embed}` `swap:false`; on-demand group `{core-vision, sd-batch}` `swap:true`, `ttl:120`. **Router mode sketch:** `llama-server --models-dir /opt/tutor/models --models-max 2` + `POST /models/load {"model":"core-vision"}` — rejected as default because per-model flag divergence (§6.2 vs §6.3) is awkward in a single router process and slot state does not survive swaps.

## Appendix C — Source references (research basis)

- llama-server flags & caching: llama.cpp `tools/server/README.md`; KV-reuse guide (7minai, 2026-07); prefix-cache verification (craftrigs, 2026-04); slots tutorial (ggml-org discussion #13606).
- mmproj capability-flag limitation: ggml-org/llama.cpp issue #21133 (2026-03).
- mtmd design (separate mmproj, encoder outside libllama): llama.cpp `tools/mtmd/README.md`.
- ik_llama.cpp: repo README (rtr repack, iqk_mul_mat, MTP for Qwen3.5, AVX2-first; UD `_XL` f16-tensor caveat).
- OpenVINO backend for llama.cpp (preview): OpenVINO 2026.1 release notes; llama.cpp `docs/backend/OPENVINO.md`.
- sherpa-onnx (Moonshine INT8, Kokoro, Piper, VAD, ws servers): k2-fsa/sherpa-onnx README + model zoo docs.
- TTS RTF planning values: sherpa TTS model docs (RPi4 RTF tables), Kokoro/Piper comparisons (2026).
- Qwen3.5 multimodal-native + Omni infeasibility on 8 GiB CPU: Qwen3.5 model cards/blog; Qwen3.5-Omni release coverage (2026-03).

*End of TDD v1.0-draft.*
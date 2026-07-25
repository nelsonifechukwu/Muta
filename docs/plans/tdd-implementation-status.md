# TDD §15 implementation status

What exists in the repo against the TDD's strict task order, as of **23 Jul 2026**. Written
so the next person can tell — without reading 4000 lines of new code — which acceptance
checks are green, which are green *in a fake*, and which cannot be attempted until the target
hardware window (9–11 Aug).

The distinction that matters: **implemented** means code + tests that run today;
**measurement pending** means the mechanism is there but its acceptance number requires a
machine or a binary this repo does not have.

| Task | State | Acceptance check | Notes |
|---|---|---|---|
| **T1** Pin & build variant A | partial | `llama-server --version` matches lock; runs on a non-AVX512 container | `deploy/versions.lock` + `deploy/build.sh` written and pin-checked (`bundle.versions`, tested). The build itself has not been *run* — needs a Linux builder. `docker/dev.Dockerfile` already builds the same flags and asserts the ISA. |
| **T2** `fetch_models.sh` + MANIFEST | implemented | hashes verify twice | `scripts/fetch_models.sh` (+ `model_specs.py`, `verify_models.sh`) — `make fetch-models` / `make verify-models`. All nine artifacts **resolved against the live Hub API and pinned to commit SHAs** in `models/pins.lock.json`; core/mmproj/asr/vad/tts/embed downloaded, hashed twice (post-download and post-copy), licences captured to `models/LICENSES/`. Three findings changed the plan — see `docs/model-provenance.md`: (1) **the Q8_0 mmproj in §4.2 does not exist** in any first-party repo, and the F16 substitute pushes the resident tier to 3.41 GiB, **over the 3.3 GiB cap**; (2) the default Piper voice (`lessac`) is **not redistributable** (Blizzard 2013 research licence) — pinned CC0 `joe` instead; (3) the sherpa-onnx VAD source repo carries **no licence at all** — pinned an MIT mirror and proved compatibility with a real sherpa instantiation. Tier B (`asr-multi`, `tts-premium`, `draft`) resolved and recorded as `fetched:false`. |
| **T3** Repo skeleton + install/stage | implemented | stage from USB onto a clean VM; corrupt one byte → refusal names the file | `bundle/layout.py`, `bundle/stage.py` (verify → copy → re-verify → warm), `deploy/install.sh`, systemd units, `etc/profile.env`. The corrupt-byte path is a test. Staging from a physical USB onto a VM is unexercised. |
| **T4** CORE-TEXT with §6.2 flags | implemented (invocation) | `/props` reflects every flag; `/metrics` scrapes | `runtime/profiles.py` emits the full §6.2 command; tests assert every load-bearing flag, and that vision omits the three flags mmproj disables. Not launched against a real engine here. |
| **T5** KV math from GGUF metadata | implemented | table committed with measured values | `runtime/gguf.py` + `runtime/kvmath.py`; reproduces the TDD's worked example to the quoted KiB and runs against the real dev GGUF. `make kv-budget MODEL=…` regenerates the table. Compute-buffer term marked PROVISIONAL. |
| **T6** Gateway skeleton | implemented | S1 end to end | `/v1/tutor/chat` (+ `/chat/stream`), sampling profiles, sessions, ladder, health/metrics. Tested against a fake engine; the real S1 needs a running llama-server. |
| **T7** Prompt layout + cache-reuse | implemented (layout) | cache-hit tokens > 60% on repeated syllabus queries | `orchestrator/gateway/prompt_layout.py` with the stable-prefix invariants tested. The 60% figure is a `/metrics` measurement against a live engine — pending. |
| **T8** Tool loop + verifier + renderer sandbox | implemented | 60-expression golden set 100%; 0 sandbox escapes | 60/60 goldens pass; escape tests cover imports, builtins, dunders, network, wall-clock, CPU. Memory-limit test is Linux-only (macOS does not enforce `RLIMIT_AS`). |
| **T9** Audio service | partial | S3 round-trip < 4 s; 60 speech goldens | Normaliser + 60 goldens + endpointing + websocket protocol are done and tested with fake engines. sherpa-onnx binaries and voices are not vendored, so ASR/TTS report unavailable and the gateway degrades to text. The < 4 s number needs the real engines. |
| **T10** CORE-VISION manager | implemented | spawn ≤ 6 s warm; L1 denial returns a friendly fallback | Spawn/TTL/deny + `systemd-run --scope` capping + image guard + ffmpeg frame command, all tested. The 6 s budget is logged against, not yet measured. |
| **T11** Embed server + FAISS + retrieve | implemented (path) | top-3 recall ≥ 90% on 50 seeded queries | Index, store, retriever, embedder-identity guard, `/internal/retrieval/search`. Recall is measured against a lexical test double — the acceptance number needs the embed server and the real corpus. |
| **T12** Suspend/resume | implemented | 30 students on 6 slots, zero cold starts after warmup | Slot save/restore client, LRU reaper with live-session protection, admission control, learning twin (atomic writes, corruption quarantine). The 30-student soak is T15. |
| **T13** Bench week scripts | not started | CSV row per cell | Needs the target box. `bench/` already has `score.py`, `profile.py`, the ADTC profiler integration. |
| **T14** Ladder + earlyoom + zram + cgroups | implemented | chaos test: balloon 1.5 GiB → L1→L3 → release → back | Ladder with hysteresis, `earlyoom.conf`, `zram-generator.conf`, `MemoryMax` on every unit. The walk-up-and-down is a unit test; the real balloon test needs the Linux box. |
| **T15** 60-minute soak | not started | SC-3, SC-4 numbers | Target hardware. |
| **T16** Clean-room package | partial | green `package.sh` + container selftest | `deploy/package.sh` and `deploy/selftest.sh` written; the `--network none` container rehearsal has not been run (no Docker daemon here). |
| **T17** Variants B/C | not started (conditional) | one-command compare report | Gated on D4 and hardware day. |
| **T18** Demo assets | not started | full SC-2 rehearsal recorded | Depends on a working vision completion call and the real models. |

## Where the new code lives

```
bundle/          manifest (sha256 x2), staging, versions.lock parsing        T1–T3
deploy/          build.sh fetch_models.sh stage.sh install.sh selftest.sh
                 package.sh · units/*.service · etc/profile.env · audio.yaml
runtime/         profiles.py (every §6.2/6.3/6.7 flag) · gguf.py · kvmath.py  T4, T5
                 vision.py (spawn/TTL/deny) · slots.py (save/restore + LRU)   T10, T12
orchestrator/
  gateway/       sampling.py · prompt_layout.py · ladder.py · sessions.py     T6, T7, T14
                 images.py (guard) · deps.py (process-wide singletons)
  tools/         sandbox.py · _worker.py · verifier.py · renderer.py · loop.py T8
                 goldens/verify_goldens.json (60 cases)
  audio/         mathspeech.py · vad.py · engines.py · service.py             T9
                 goldens/speech_goldens.json (60 cases)
  retrieval/     embedder.py · index.py · app.py                              T11
  pedagogy/      twin.py                                                      T12
```

## Things worth knowing before changing any of it

- **The flags are the memory budget.** `runtime/profiles.py` is the only place a context size,
  slot count or thread count may be written down. A hardcoded `-c` elsewhere silently
  re-prices every slot.
- **"Unverified" is not "wrong."** `VerifyOutcome.checked` is separate from `.verified` on
  purpose; collapsing them is how a marking report becomes fiction.
- **RAG chunks are stable-sorted, not relevance-sorted.** That looks like a bug and is a
  cache-reuse decision (§7.3). There is a test that fails if someone "fixes" it.
- **Degradation is immediate, recovery is deliberate.** The ladder has hysteresis in one
  direction only.
- **Nothing here has run on the target box.** Every number in this repo that is not derived
  from a file's own metadata is a planning value, and the ones that matter are labelled.

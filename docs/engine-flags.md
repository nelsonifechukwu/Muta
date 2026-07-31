# llama.cpp b10035 — behaviours the flags depend on (measured, not assumed)

Verified 2026-07-31 against the pinned build (`602f828`) with
`models/core/Qwen3.5-4B-Q4_K_M.gguf`, and re-verified whenever the pin moves.
`runtime/config.py` defaults and `docker-compose.yml` comments cite this file.

## Speculation is gated by --spec-type

`--spec-type` defaults to `none`; `--spec-draft-model` alone is silently ignored (no
draft load, no `[spec]` log lines). The dev branch shipped exactly that dead
configuration. `runtime/server.py:_speculation_flags` now always emits `--spec-type`.

## Draft vocab compatibility is enforced

Qwen3-0.6B (vocab 151,936) is rejected for Qwen3.5-4B (vocab 248,320):
`the target and draft vocabs are not compatible`. Only Qwen3.5-family drafts are
viable; the roster's tier-B Qwen3.5-0.8B (`fetch_models --with-draft`) is the draft of
record. **Verified 2026-07-31 (Task 8, docker mode, `--spec-draft-model
models/draft/Qwen3.5-0.8B-Q4_K_M.gguf`): the 0.8B draft is ACCEPTED, not rejected.**
`GET /slots` reports `"speculative":true` on both slots; the startup log never emits a
`vocabs are not compatible` line; and live per-request timings confirm real drafting —
turn 1 drafted 187 tokens (183 accepted), turn 2 drafted 134 tokens (133 accepted),
engine-reported `draft acceptance = 0.97861` and `0.99254` respectively. **Combined
acceptance 316/321 = 98.4%.** See "draft-simple speculation is net-negative under CPU
emulation" below for the throughput verdict that acceptance rate does *not* by itself
guarantee.

## The hybrid architecture makes state, not KV, the RAM driver

Qwen3.5-4B runs full attention on 8 of 32 layers (`full_attention_interval = 4`);
per-token KV is ~24.5 KiB (q8_0 K + f16 V) — `runtime/kvmath.py` models this. The other
24 layers carry ~50.25 MiB of f32 recurrent state per slot, and every context
checkpoint copies it. Defaults before capping: `-np auto` → 4 slots, 32 checkpoints per
slot, `--cache-ram 8192` (each cached conversation ≈ 57 MiB) — measured RSS drift
2.9 → 4.8 GiB in four short requests. Caps now live in `RuntimeConfig`
(`n_parallel=2, ctx_checkpoints=4, cache_ram_mib=256`).

## Multi-turn prefix reuse works via checkpoint restore

With thinking-stripped history (the product's replay shape), turn 2 of a 269-token
conversation restored the end-of-prompt checkpoint and processed only 149 tokens.
Reuse must be re-verified whenever `ctx_checkpoints` changes — too low a cap silently
degrades to full re-prefill.

**Verified 2026-07-31 (Task 8 two-turn probe, `--ctx-checkpoints 4`):** reproduced twice
independently (once with `--spec-type draft-simple`, once with `--spec-type none`,
otherwise identical caps/prompts/seed) — both runs restored the same checkpoint: turn 2's
`usage.prompt_tokens` was 65 but the engine's `timings.prompt_n` was only 30 (35 tokens,
54% of the turn, served from the restored checkpoint instead of re-prefilled). The slot
log confirms the mechanism explicitly: `selected slot by LCP similarity, sim_best = 0.569
(> 0.100 thold), f_keep = 0.126` — identical in both runs, i.e. checkpoint restore is
governed by `--ctx-checkpoints` alone and is unaffected by whether speculation is active.

## ngram speculation needs non-default params on this workload

`ngram-simple` at engine defaults (lookup N=12) produced zero drafts on tutoring
turns. `size-n 4 / size-m 12` measured 12–22% token acceptance (mean accepted run
3.3). Zero RAM; net-neutral under emulation (compute-bound); expected to pay only on
bandwidth-bound hardware. Wired as `spec_type: "ngram-simple"`.

## draft-simple speculation is net-negative under CPU emulation (measured 2026-07-31)

High acceptance does not imply a speedup once the draft model's own forward passes are
counted. Same two-turn probe, same caps, only `--spec-type` changed:

| config | turn 1 tok/s | turn 2 tok/s | avg tok/s | llama-server RSS |
|---|---|---|---|---|
| `--spec-type none` (no draft) | 7.08 | 6.36 | **6.72** | 4.44 GiB (ps RSS) |
| `--spec-type draft-simple` + 0.8B (98.4% accepted) | 4.61 | 4.93 | **4.77** | 5.46 GiB (ps RSS) |

Turning speculation on cost **−1.95 tok/s (−29%) and +~1.0 GiB**, despite 98.4% of
drafted tokens being accepted. On this emulated `linux/amd64`-under-Docker-Desktop host,
decode is compute-bound (verifying a draft still costs a forward pass on the 4B for every
accepted token, plus the 0.8B's own forward pass to produce it) — the memory-bandwidth
savings speculative decoding is designed to capture do not materialize. The mean accepted
run length (`draft_n / (accepted "runs")`, roughly 4–5 tokens/round per the request
timings) does not compensate. **Do not treat this as the final verdict**: this is a
dev-host, emulated-CPU measurement (`bench/optimization-log.md` tags it
`dev_host_provisional` and parks it); the x86 target box, which is genuinely
bandwidth-bound rather than compute-bound under emulation, is the number that decides
whether `spec_type: draft-simple` ships as the default.

## Misc

- `-np -1` (auto) resolves to 4 slots with `kv_unified = true` at `-c 2048`.
- Default threads = ALL cores for decode and prefill (`n_threads = 10 (n_threads_batch = 10)`
  in the 10-vCPU VM) — compose pins 8/10.
- `--defrag-thold` is deprecated in this build (profiles.py still passes it — harmless).
- Weight loading repacks ~1.3 GiB of the 4B's tensors into anonymous RAM
  (`CPU_REPACK`) for AVX2 kernels; model memory ≈ 2.6 GiB total, context ≈ 250 MiB at
  the old 4-slot default, compute ≈ 31 MiB at `-ub 128`.
- This build's `llama-server.log` at `verbosity = 3` does **not** print the
  `context checkpoints enabled, max = N` or a draft-model "loaded" banner the plan
  expected — `n_slots = 2` is the only one of the four grep targets in
  `load_model: initializing, ...` that actually appears at startup. Verify checkpoint
  and draft behaviour functionally instead: `GET /slots` → `"speculative":true/false`
  per slot, and per-request `timings.draft_n` / the `draft acceptance = ...` log line
  for speculation; `timings.prompt_n` well below `usage.prompt_tokens` on turn 2, plus
  the `selected slot by LCP similarity` log line, for checkpoint restore.
- `docker stats --format '{{.MemUsage}}'` was internally inconsistent on this
  Docker-Desktop-for-Mac host: it reported the speculation-on backend (two loaded
  models) at a *lower* figure (3.995 GiB) than the speculation-off backend (one model,
  4.553 GiB) — impossible if both are true resident-set readings, and also below the
  in-container `ps aux` RSS of the `llama-server` process alone in the same speculation-on
  container (5.46 GiB). Cross-check with `docker compose exec backend ps aux` (or
  `/proc/<pid>/status`) before trusting a `docker stats` delta on macOS; the RAM figures
  in `bench/optimization-log.md`'s 2026-07-31 rows use the `ps aux` numbers for exactly
  this reason. This matches the project's own telemetry design
  (`orchestrator/telemetry.py`), which already treats RSS as unmeasurable (→ `null`) on
  Docker/macOS.

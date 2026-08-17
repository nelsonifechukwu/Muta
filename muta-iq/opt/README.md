# muta-iq/opt — optimization workspace (2026-08-17)

Two sessions live here. **Night:** the S_eff/S_perf study of `model/bitcpm4-8b-tq2_0.gguf`
(`docs/REPORT.md`, streaming engine, SVD, vocab pruning). **Day:** the model re-selection for the
audit binary that produced the shipped `model/muta-tutor-qwen3-1.7b-q4_0.gguf` — start with
**`research/DECISION_BRIEF.md`**, then `results/bakeoff.tsv`, then the root `REPORT.md`.

| day-session path | what |
|---|---|
| `research/r1..r7*.md`, `research/DECISION_BRIEF.md` | template/rules, judging mechanics, model landscape, audit-kernel facts, template tricks, fine-tune/data plan, competitor intel, synthesis |
| `scripts/bakeoff.sh`, `scripts/eval_math.py`, `eval/` | the bake-off battery (stock bench + generic-kernel proxy + GSM8K-40 + tutoring transcripts + arc_easy) and its results in `results/bakeoff.tsv`, `eval/results/*.json` |
| `scripts/bake_system_prompt.py`, `scripts/drop_tensor.py`, `scripts/finalize_model.sh` | the pipeline that turns a candidate GGUF into the shipped file (persona template, sampling keys, name; drop duplicated head) |
| `audit-bench/` | GitHub-Actions workflow that rebuilds the exact audit binary on a free x86 runner (push it to run) |
| `candidates/` (gitignored) | downloaded/derived candidate GGUFs |


| path | what |
|---|---|
| `docs/REPORT.md` | the report: scoring physics, streaming, mmap, SVD, GGUF levers, recommendation |
| `docs/PLAN.md` | the plan written before the work; `docs/STREAMING_ENGINE.md` the engine design |
| `llama.cpp/` | shallow clone of llama.cpp **b10360** + the `[muta]` residency-window patch (`src/llama-residency-lite.*`, small hooks in `llama-mmap`, `llama-model`, `llama-context`, `llama.cpp`); build dir `build-cpu/` (gitignored) |
| `llama.cpp-generic/` | copy with `MUTA_FORCE_GENERIC` (audit-kernel proxy), see `results/audit_kernel_proxy.md` |
| `scripts/prune_vocab.py`, `scripts/verify_prune.py` | CJK vocabulary pruning + verification (adopted) |
| `scripts/bench_rss.py` | llama-bench wrapper sampling RSS exactly like the profiler; `stock_bench.sh`, `engine_sweep.sh`, `engine_profile*.sh` drive it |
| `scripts/with_lock.py` | machine-wide exclusive lock — every heavy run went through it |
| `scripts/memprobe*.c` | Darwin mmap/RSS primitive probes; `rss_trace.py` 20 ms RSS tracer |
| `scripts/svd/` | SVD spectra tooling; `results/svd/svd_report.md` |
| `results/*.tsv, *.md, *.log` | every measurement (bench_log.jsonl has full RSS timelines) |
| `models/` (gitignored) | derived GGUFs: `bitcpm4-8b-tq2_0-envocab64.gguf` (= `../model/bitcpm4-8b-tq2_0-envocab.gguf`, hard-linked), `bitcpm4-8b-tq1_0.gguf`, head/embd requant variants |

Reproduce the submission model: `python3 scripts/prune_vocab.py ../model/bitcpm4-8b-tq2_0.gguf ../model/bitcpm4-8b-tq2_0-envocab.gguf`
(sha256 `069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d`).

Run the engine: `MUTA_STREAM=1 MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0 MUTA_NO_REPACK=1 MUTA_UBATCH=128 llama.cpp/build-cpu/bin/llama-bench -m ../model/bitcpm4-8b-tq2_0-envocab.gguf -p 512 -n 128 -ngl 0`
(add `MUTA_STREAM_PIN_MB=1500` for the ~15 tok/s point).

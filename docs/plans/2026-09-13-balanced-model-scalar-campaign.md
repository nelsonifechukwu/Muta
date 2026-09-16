# Balanced model scalar campaign

## Objective

Compare the immediate challengers from the Local AI Zone census and the follow-up candidate
list with Muta's fine-tuned Qwen2.5-1.5B control under one reproducible ADTC-style protocol,
then produce a ranked CSV and a detailed Markdown report using the same 100 mathematics and
science prompts as `report.md`.

## Candidate artifacts

1. Muta fine-tuned Qwen2.5-1.5B Q4_K_M (control)
2. LFM2.5-1.2B-Thinking Q4_0
3. MiniCPM5-1B converted from the official F16 artifact to pure Q4_0
4. Qwen3.5-2B Q4_0
5. Qwen3-1.7B Q4_0
6. LFM2.5-2.6B Q4_0
7. MiniCPM5-2B Q4_K_M
8. LFM2.5-2.6B QAD-Q4_0
9. MiniCPM5-1B Q4_K_M (quantization control for the pure-Q4_0 artifact)
10. Qwen3.5-2B Q4_K_M (quantization control for the Q4_0 artifact)
11. VibeThinker-1.5B Q4_K_M
12. Falcon-H1-Tiny-R-0.6B Q4_K_M
13. OpenReasoning-Nemotron-1.5B Q4_K_M

LFM2.5-1.2B-Thinking Q4_0 and Qwen3-1.7B Q4_0 already represent two entries in the follow-up
list, so they are not run twice. Spark-X2.5-1.7B remains outside the scored set because the
profiler-pinned llama.cpp b10175
does not support its architecture. Record that incompatibility in the report rather than mixing a
newer runtime into the comparison.

## Measurement protocol

- Use the GCP `muta-vm` x86 cloud proxy: `n2-custom-4-8192`, 2 physical cores / 4 threads,
  Ubuntu 22.04, 8 GB class, no swap.
- Stop the Muta gateway/engine before measurement and prevent concurrent campaign runs with an
  exclusive `flock` lock.
- Execute one model and one measurement process at a time. Before every measured run, reject
  unexpected `llama-*`, profiler, or evaluation processes.
- Use the profiler-compatible scalar llama.cpp b10175 binary with AVX, AVX2, FMA, and F16C off.
- Retain a secondary matched run with the portable vector build (AVX2, FMA, and F16C on;
  AVX-512 off), in accordance with the standing two-configuration benchmark protocol. Do not
  use the vector result to rank the official-profiler candidates.
- Run the profiler invocation exactly: `llama-bench -p 512 -n 128 -ngl 0 -o json`, with five
  internal repetitions and no explicit thread override.
- Sample whole-child-tree RSS every 0.1 seconds. Preserve that direct measurement and report a
  separately labelled profiler estimate formed by adding the campaign's fixed 45 MiB Python-root
  allowance; use the latter in the score calculation.
- Run ARC-Easy-500 through `adtc_profiler.accuracy` for the quantitative accuracy proxy. The
  profiler accuracy wheel has its own compiled CPU path, so do not describe that stage as scalar.
- Replay the fixed 100-prompt battery from `report.md` using raw completion, context 2,048,
  temperature 0, seed 42, 256 generated tokens for multiple choice, and 512 for written prompts.
- Replay the ten exact Gate 1 automated and human-judge prompts through each GGUF's embedded chat
  template with no external system prompt. Use the same deterministic sampler and runtime for all
  models, preserve every response, and rank them with a fixed prompt-specific 100-point rubric.

## Score and reporting

- Compute the executable-profiler score with fixed 15 tok/s:
  `0.50 × accuracy + 0.30 × min(TPS / 15, 1) × 100 + 0.20 × (7 − RSS_GiB) / 7 × 100`.
- Treat ARC-Easy as a profiler proxy, not the unavailable panel score.
- Report the 100-prompt battery separately by math/science and multiple-choice/written sections.
- Preserve raw outputs, model SHA-256 values, source revisions, commands, binary identity,
  hardware state, failures, and timestamps.
- Rank only candidates that load, complete all required measurements, and remain below 7 GiB RSS.

## Deliverables

- `bench/measurements/campaign-20260913-balanced-models/results.csv`
- `bench/measurements/campaign-20260913-balanced-models/report.md`
- `bench/measurements/campaign-20260913-balanced-models/judges-ranking.csv`
- `bench/measurements/campaign-20260913-balanced-models/judges-report.md`
- Raw throughput, ARC-Easy, prompt-response, adjudication, manifest, and system-evidence files in
  the same directory.

## Acceptance gates

1. Every artifact has an immutable source revision, byte size, and verified SHA-256.
2. No two model processes overlap; the campaign log proves serial execution.
3. All scored candidates use the same scalar binary and benchmark command.
4. All scored candidates have one ARC-Easy-500 row and all 100 prompt responses.
5. Summary arithmetic reproduces from raw evidence and the repository score implementation.
6. The report distinguishes measurement, inference, and unsupported upstream claims.
7. After measurement, restore the previously running Muta gateway service and verify health.

## Accuracy execution update

The scalar and vector throughput measurements and ARC-Easy-500 have completed for all thirteen
compatible artifacts. The first nine models have complete scalar raw-completion STEM runs.
Interrupted scalar runs for the remaining four are retained, but excluded from complete-run
comparisons. Those four are now being screened with the matched b10175 vector server on GCP.
Do not combine duplicate prompt responses or pool execution contexts.

Mac Metal inference is permitted for a separate accuracy screen, not for laptop throughput,
RSS, or an official-profiler score. First validate the exact fine-tuned control already present
on the Mac, using b10175 source, identical GGUF bytes, prompts, sampler and output limits.
Record the hardware, GPU offload, server identity and settings. Leave the active GCP batch
uninterrupted while checking this path. Moving the remaining artifacts depends on actual
transfer speed. Confirm finalists through scalar GCP chat inference before a submission claim.

The raw STEM option parser required correction. Recompute extracted answers from saved text;
retain the original records. Selected-letter correctness does not adjudicate the explanation.
Judges' keyword scores are provisional diagnostics, not a substitute for reviewed answers or
the competition panel's grade. Incomplete runs must remain unranked.

The campaign lock prevents competing campaign runners, not unrelated user builds. A packaging
watchdog records pauses when known build processes appear. Affected response durations are
not throughput evidence; host snapshots and pause logs are diagnostic rather than proof of
continuous exclusive use. Preserve interrupted outputs and disclose these limitations.

## Matched accuracy review and response delivery

The Mac queue finished twelve complete 100-prompt STEM sets and twelve complete ten-prompt
Gate 1 sets. Falcon produced three partial Gate 1 records and failed both generation stages.
The vector GCP remainder stopped after two complete STEM sets, on Falcon. The independent
`muta-judges-scalar-20260914.service` now runs the scalar Gate 1 replay; do not restart the
obsolete after-STEM service or wait for its unmet four-model prerequisite.

- Grade all twelve Mac STEM sets as one matched hardware treatment. Keep original scalar
  and vector GCP STEM evidence and its assessments separate; never fill a Mac ranking with
  a score measured on another backend.
- Retain central-answer correctness and instruction-complete pass as separate diagnostics.
  The latter requires correct supporting reasoning and all substantive requested components,
  including a real independent check when requested. An unsafe extra recommendation fails
  that stricter assessment even if a safe action also appears.
- Keep the existing ten-question local Gate 1 rubric. Grade delivered final text only;
  do not count unfinished thinking as a completed answer. These are provisional assistant
  assessments, not organizer scores.
- Publish every prompt and unedited returned answer in separate, source-linked transcript
  files. Preserve separately returned reasoning, completion state and failed/missing requests.
  Link these files from a compact evidence index. Do not embed generated text as executable HTML.
- Validate model hashes, exact prompt IDs/text, execution context, source hashes, and duplicate
  records before joining responses or manual grades. Hash-verified identical answers can reuse
  a semantic assessment, but the new assessment must retain its own source/context.
- The replay restores unreadable currency glyphs to ₦ in the chalk and rice prompts. Other
  wording matches the user-supplied Gate 1 evidence, ignoring whitespace. Describe this
  normalization rather than claiming a byte-identical export.
- Add unit tests and independent review for the evidence/report join. The final report must
  remain incomplete until the required replays and adjudication are complete.

## Completed comparison and exceptions

The GCP queue ended with thirteen performance/ARC records and twelve complete scalar Gate 1
sets. Falcon failed after five captured Gate 1 responses and remains unranked; Spark remains
runtime-excluded. The authorized Mac accuracy screen supplies twelve matched, manually
assessed 100-prompt STEM sets and twelve Gate 1 sets, kept separate from GCP. Earlier partial
GCP STEM attempts are preserved, not presented as thirteen completed scalar STEM sets.

Final `results.csv`, `judges-ranking.csv`, `report.md`, `stem-report.md` and `judges-report.md`
are delivered under the campaign directory, with all saved responses linked. Source identity,
grades, ranks and score arithmetic were independently reconciled. The evidence/join test suite
passes 196 tests. Composite totals remain estimates and no full physical-laptop audit or
continuous host-exclusivity claim is made.

The restoration acceptance gate was not met: Ops Agent resumed, but the gateway fails native
UI asset validation because SVG dependencies are omitted from the export. No inference remains.
The failure and repair boundary are documented in `host-completion.md`; unrelated UI repair is
not included in this benchmark completion. No dashboard edits, commits or pushes were made.

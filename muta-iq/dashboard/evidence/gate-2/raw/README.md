# Balanced-model scalar campaign

This directory contains the matched GCP screen of the Local AI Zone shortlist, the follow-up
candidate set, and Muta's fine-tuned Qwen2.5-1.5B control.

## Final reports

- [Campaign report](report.md): methods, results, limitations and model selection evidence.
- [Results CSV](results.csv): GCP scalar/vector measurements, estimated composites and
  separately labelled accuracy assessments.
- [Judges ranking CSV](judges-ranking.csv): separate GCP scalar and Mac Gate 1 rankings.
- [STEM assessment](stem-report.md): the matched Mac 100-prompt test and category results.
- [Gate 1 assessment](judges-report.md): local final-output rubric results and limitations.
- [GCP scalar answers](gcp-judges-responses.md) and [Mac answers](prompt-responses.md): every
  captured prompt and unedited response, with missing positions retained for failed models.

`results-now.csv` and `results-now.md` retain earlier partial snapshots. Use the final files
above for the completed campaign; older snapshots are not its current status.

## Completed coverage and failures

Scalar throughput, vector throughput and ARC-Easy-500 each have thirteen completed rows.
The independent GCP scalar Gate 1 replay has ended with 125 responses: twelve models have
all ten prompts and source-validated manual assessments; Falcon returned five responses
before a [chat-output parsing failure](failures/falcon-gcp-scalar.md). Its incomplete set has
no judge score or rank. Spark failed the runtime gate and was excluded from these thirteen.

The Mac M4 Pro screen uses the same b10175 source and verified GGUF artifacts with Metal
offload. Twelve models completed all 100 STEM and ten Gate 1 requests and have separate
manual assessments. Falcon returned three partial Gate 1 responses before a parsing failure;
it has no Mac STEM responses or ranked grade. Complete request coverage does not imply
that every answer finished within the token limit or was correct.

The earlier GCP STEM attempts remain separate: nine complete original scalar sets, two
overlapping partial scalar attempts for Qwen3.5 Q4_K_M, and complete vector sets for
Qwen3.5 Q4_K_M and VibeThinker. The vector batch stopped on Falcon before Nemotron.
The [attempt inventory](gcp-stem-attempts.md) records their different configurations and
coverage. Do not combine attempts or pool them with Mac responses.

## Interpretation

Scalar and vector throughput are measured separately on GCP. ARC-Easy-500 is one shared
accuracy proxy from the official accuracy path, not paired scalar/vector accuracy tests.
The composites combine that proxy with measured throughput and estimated profiler RSS
(measured benchmark process-tree RSS plus a 45 MiB Python-root allowance). They use a
15-token/s performance cap; they are not end-to-end official-profiler scores. GCP temperature
is unavailable, so no thermal penalty is applied in the estimates.

Gate 1 uses each GGUF's embedded chat template and a **local 1,024-token output limit**,
including reasoning. This limit is not a confirmed organizer requirement. Only delivered
final text earns rubric points; separate reasoning and thinking blocks do not. STEM instead
uses raw completion, with 256 tokens for multiple choice and 512 for written responses,
and assesses the full returned text. These tests measure different behavior.

All semantic grades are local assistant assessments, not official panel grades. Selected
disputed answers received independent review; the STEM policy and its refinements are
recorded in [ADJUDICATION.md](ADJUDICATION.md). Mac timings and memory do not supply laptop
performance scores. No one ranking establishes a universal best model.

## Evidence

- `manual-stem-mac/`: matched Mac complete-pass and core-correctness assessments.
- `manual-stem/`: three original GCP scalar STEM assessments; other GCP STEM captures
  do not have complete semantic reviews.
- `manual-judges/`: source-bound Mac Gate 1 criterion assessments.
- `manual-judges-gcp/`: source-bound GCP scalar Gate 1 criterion assessments.
- `artifacts.csv`: immutable source revisions, file sizes, hashes, licences, and runtime gates.
- `load-gate-extension.tsv`: compatibility checks for the added artifacts. The full
  runtime-gate decisions, including Spark's exclusion, are in `artifacts.csv`.
- `raw/throughput.jsonl`: five-repeat scalar b10175 pp512/tg128 evidence and RSS samples.
- `raw/vector-throughput.jsonl`: matched five-repeat portable vector-proxy evidence.
- `raw/accuracy.jsonl`: ARC-Easy-500 from the official accuracy path.
- `raw/stem-responses.jsonl`: original scalar responses, including an interrupted model.
- `raw/stem-events.jsonl`: lifecycle events for the original scalar response batch.
- `raw/judges-responses.jsonl`: 125 captured GCP scalar Gate 1 responses.
- `raw/judges-events.jsonl`: GCP scalar lifecycle events, including Falcon's failure.
- `mac-accuracy/`: separate per-model Mac STEM/Gate 1 responses and configurations.
- `scalar-judges-independent-launch.md` and `judges-isolation.log`: scalar replay launch
  and isolation checks. These are not continuous host-utilization measurements.
- `raw/throughput.jsonl`, `raw/vector-throughput.jsonl` and the source-bound manual
  reviews retain benchmark/server identities and execution settings.
- [Host completion](host-completion.md): benchmark termination and service restoration
  checks. Ops Agent is active; the gateway remains unavailable because native UI assets
  fail verification.

The control pilot in `mac-pilot-runtime.md` predates the explicit 256 MiB prompt-cache
ceiling and is not pooled with the main Mac screen.

GGUF files are stored on the VM under this directory's `models/` subdirectory and in the
ignored `bench/.artifacts/mac-balanced-models/` directory on the Mac. They are not copied
into Git.

## Reproduction

`download_models.sh` fetches each exact upstream artifact and verifies its size and SHA-256.
MiniCPM5 is then converted from the recorded F16 source with:

```bash
llama-quantize --pure MiniCPM5-1B-F16.gguf MiniCPM5-1B-Q4_0.gguf Q4_0
```

The scored workload is:

```bash
llama-bench -m MODEL -p 512 -n 128 -o json -ngl 0 -r 5
```

The initial and extension runners both hold `/tmp/muta-benchmark.lock`, stop the Muta gateway
and Google Ops Agent, run one model at a time, and attempt to restore both services on exit. The
extension adds quantization controls and the seven distinct rows contributed by the follow-up
candidate list; models already present in the initial batch are not repeated. Scalar results
determine the estimated composite ordering. The vector proxy remains a secondary comparison.

The judge-prompt ranking is reported separately from the estimated profiler total. It uses the ten
automated and human prompts retained in the Muta ADTC evidence, a fixed local 100-point rubric,
and the bare GGUF chat path with no external system prompt. Unreadable currency glyphs are
restored to ₦ in the chalk and rice prompts; other wording is unchanged except whitespace.
Keyword matches do not establish mathematical correctness or explanation quality. Review
complete answers, contradictions, truncations and repeated-prompt consistency before selection.

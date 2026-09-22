# Fresh-warm Oracle export: conditional handoff

Prepared from local source and small existing receipts only. **Not executed;
not a runtime admission or a claim that training completed.** This resolves the
historical CSD3/unresolved-path row in the full-stage export handoff. It changes
neither frozen training nor the completed clean/continuation exports.

Root independently reviewed the candidate/parent/selection mapping and CLI
flags against the existing parsers on 19 September. The author checked all
three argument blocks and shell syntax. This approves only the conditional
handoff; fresh terminal, byte-hash and runtime admission checks remain required.

## Mapping and prerequisites

| Item | Required identity |
|---|---|
| Candidate | `full-best-warm-private-enriched` |
| Actual run | `$WFE_CAMPAIGN/runs/full/full-best-warm-private-enriched` |
| Merge parent | Original Muta v1, tree `02add79d0a5d451c7b75a986a4d3154bf6a98e23f12d9f913f00036c1909fec8` |
| Adapter / export tokenizer | This completed run's `adapter/`, never the pilot or parent tokenizer |
| Initialization / resume | Fresh adapter; none / none; no pilot-exposure credit |
| Planned first output | `$WFE_CAMPAIGN/exports/full-v3/warm-fresh-bestdev-v1` (must be absent) |
| Fixed model name | `Muta-Round2-Full-warm-fresh-r16-lr5e6-300350-bestdev` |

First preserve and verify actual `COMPLETED.json`, manifest, metrics JSONL/CSV,
curves and selected/checkpoint inventories; require no RUNNING/FAILED conflict,
4693 completed steps, 300350 train rows, 5000 dev rows and frozen config identity.
Confirm supervisor/launcher/trainer have exited; inspect any surviving descendants
and the GPU rather than assuming an exited supervisor proves idle. Preserve the
executed relocation wrapper `bcc54f70874bdc0b3686d5acb25d233e9dc7733d105f098dcb049d4d2cc2bfed`,
its exit receipt and the cancelled CSD3 history; do not substitute the unexecuted
local hardening draft.

Selection is the minimum scheduled dev loss at 1174/2347/4693, with Trainer's
recorded tie choice. **Do not assume 4693 wins.** Report exported step/exposures
separately from the completed full stage: 1174→75136, 2347→150208, 4693→300350.
The existing preflight checks these joins and rejects own-stage resumes/retries.

## 1. Future offline artifact preflight

Root must hash-check the existing frozen sources before use: preflight
`79e2cd8b226aac23b64aa398a98a439096579ddd97bb38f1387e7805f1086e57`,
exporter `ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be`,
helper `ded88829f91109eb6664d3cf177cde7a8c9665cab731204213ab33047b8fe121`.
Use the established sanitized offline environment and exclusively new receipt
paths below; their parent already exists. No command in this document was run.

```bash
WFE_CAMPAIGN=/lambda/nfs/awf-tmp/muta/campaign-20260918
WFE_TRAIN="$WFE_CAMPAIGN/code/fullstage-v3-20260918T2035"
WFE_EXPORT_V1="$WFE_CAMPAIGN/code/full-export-v1-20260918T2203"
WFE_EXPORT_V2="$WFE_CAMPAIGN/code/full-export-v2-20260919T0034"
WFE_EVIDENCE="$WFE_CAMPAIGN/code/full-export-evidence-v1-20260918T2227"
WFE_PROOF="$WFE_CAMPAIGN/provenance/full-export-v1"
WFE_PY=/home/ubuntu/muta-finetune/.venv/bin/python
WFE_RUN="$WFE_CAMPAIGN/runs/full/full-best-warm-private-enriched"
WFE_OUT="$WFE_CAMPAIGN/exports/full-v3/warm-fresh-bestdev-v1"
WFE_PREFLIGHT="$WFE_PROOF/warm-fresh-preflight-v1.json"

"$WFE_PY" -B "$WFE_EXPORT_V1/preflight_full_stage_export.py" \
  --full-config "$WFE_TRAIN/provenance/configs/full-runs-v3.json" \
  --expected-full-config-sha256 da828b9146415ca822fecf1961808b914e9666cf7452de34e7704b97f83675da \
  --candidate-id full-best-warm-private-enriched --run-dir "$WFE_RUN" \
  --training-code "$WFE_TRAIN/model-development/finetune" \
  --base /home/ubuntu/muta-finetune/runs-metric/qwen25-bf16-r16-licensed-mcq-lr2e5-500/merged_16bit \
  --base-lineage "$WFE_CAMPAIGN/provenance/warm-lineage.json" \
  --dataset-manifest "$WFE_CAMPAIGN/data/muta-stem-v2-sft-300k-quality-first-20260917-v1/manifest.json" \
  --validation-manifest "$WFE_CAMPAIGN/data/round2-dev-5000/manifest.json" \
  --exporter "$WFE_EXPORT_V1/merge_and_quantize.py" \
  --expected-exporter-sha256 ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be \
  --llama-cpp /home/ubuntu/llama.cpp-b10175 \
  --reference-export-manifest "$WFE_TRAIN/provenance/exports/pilot-warm-r16-lr5e6/quantization-manifest.json" \
  --expected-reference-export-manifest-sha256 67077e17743327aacbade27f4c497b6fd214bcf22aa07c99a45e21b5e34edc69 \
  --output "$WFE_PREFLIGHT"
```

Review the actual new receipt and externally pin its byte SHA as
`WFE_PREFLIGHT_SHA`; do not copy another candidate's receipt or predict its hash.
The pilot reference binds conversion history only, not fresh-warm initialization.
Compare saved tokenizer/template bytes to the already inspected clean saved
tokenizer; exact matching bytes can reuse that scoped semantic evidence. Changed
bytes require separate inspection. Neither preflight nor scalar GGUF metadata
proves complete loaded tokenizer parity; preserve the earlier no-Torch-import
control discrepancy.

## 2. New measured runtime draft, then separate reviewed admission

Collector SHA is `24ca98c0900c8e761c4d969c720e268dff504d9f910a71790a3800d17bf29f24`.
It deliberately loads original v1 launcher `16f10222dab4be4facc7e04e6f6a6215d6d0d17d312887a4308445a85df9abb0`
for the unchanged metadata probe; **do not pass the v2 launcher to this collector**.

```bash
"$WFE_PY" -B "$WFE_EVIDENCE/collect_full_export_runtime_evidence.py" \
  --launcher "$WFE_EXPORT_V1/launch_full_stage_export.py" \
  --preflight-receipt "$WFE_PREFLIGHT" --expected-preflight-sha256 "$WFE_PREFLIGHT_SHA" \
  --python "$WFE_PY" --git /usr/bin/git --nvidia-smi /usr/bin/nvidia-smi --ldd /usr/bin/ldd \
  --planned-output "$WFE_OUT" --gpu 0 --expires-in-seconds 7200 \
  --output "$WFE_PROOF/warm-fresh-runtime-evidence-v1.json"
```

Review actual host/interpreter/import/package/tool/dependency identities and
non-hermetic coverage. Candidate, preflight SHA, output-derived environment and
times must belong to this run; never relabel an old admission or merely extend
its expiry. Only after fresh resource review create a separate
`warm-fresh-runtime-admission-v1.json` with the accepted admission kind and
externally record its actual byte SHA as `WFE_ADMISSION_SHA`. A draft is not
admission; no admission is created by this plan.

## 3. One guarded GPU export, only after all preceding gates

Use corrected launcher SHA `44be7b159af96d12c99005cc0fe3ab829556070b8352369c83b77c780ef108cd`.
Recheck the auxiliary profile and its currently measured source/executable files;
old hash availability alone is insufficient. The launcher retains the shared
GPU lock into inspected descendants, reruns artifact/runtime/idle gates, claims
a new output and preserves failures. Do not hold a competing outer lock or run
the exporter directly. Use the established durable launch/PID/log capture.

```bash
"$WFE_PY" -B "$WFE_EXPORT_V2/launch_full_stage_export.py" \
  --preflight-receipt "$WFE_PREFLIGHT" --expected-preflight-sha256 "$WFE_PREFLIGHT_SHA" \
  --runtime-admission "$WFE_PROOF/warm-fresh-runtime-admission-v1.json" \
  --expected-runtime-admission-sha256 "$WFE_ADMISSION_SHA" \
  --python "$WFE_PY" --mode gpu --gpu 0 --max-seconds 7200 --output "$WFE_OUT" \
  --auxiliary-profile "$WFE_PROOF/auxiliary-profile-v1.json" \
  --expected-auxiliary-profile-sha256 c068eb257c66adb87ae72757fcae3a5cff945c484dbde23ca2357b02677cc221
```

Expected output basename is
`Muta-Round2-Full-warm-fresh-r16-lr5e6-300350-bestdev-Q4_K_M.gguf`;
its bytes/SHA are unknown until export. Verify new terminal/manifest/log/hash
joins, metadata and actual load/normal-stop behavior; then add it to a **new**
five-model matched evaluation. Preserve the four-model smokes. Deliver only one
verified Mac GGUF and selected adapter copy under the existing no-duplicate
policy. Do not rerun or copy completed clean/continuation exports.

# Muta proof of training

This directory is the Gate 2 evidence bundle for the 2026-09-18 Muta round-two
fine-tuning campaign. Generated claims are accepted only when their files and
SHA-256 receipts agree.

The [Gate 2 checklist](GATE2_CHECKLIST.md) links each requested evidence item and
explicitly separates present files from rights, reviewer-access, submission and
independent-qualification gaps. It is an evidence index, not submission clearance.

The separate practical 2,000-question comparison is now complete: **10,000
responses across five GGUFs**, with a frozen structured-answer decision to
retain previous Muta. See the [current recommendation and score tables](results/PRACTICAL_WINNER_DECISION.md)
and [sealed primary comparison](results/practical-five-2000-20260919/README.md).
Its fixed [100-response diagnostic](results/practical-five-2000-semantic-review-20260919/README.md)
is complete with two independent agent reviews per response and retained
reconciliations; no primary scores changed. Fresh-instance coverage is not whole-family independence,
and no default file was swapped. The earlier snapshot below remains historical.

## Campaign matrix

| Control or treatment | Parent | Purpose |
|---|---|---|
| Upstream control | pinned Qwen2.5-1.5B-Instruct | Unmodified matched-export control |
| Incumbent Muta | published Q4_K_M, SHA `a750d00d...` | Previous best model |
| Clean pilots | pinned Qwen + 20,000 selected rows | Initial screening, not full-data training |
| Warm pilots | merged incumbent Muta + 20,000 selected rows | Initial screening, not full-data training |
| Full clean | pinned Qwen + all 300,350 rows | Training complete; exported; one verified Mac GGUF copy |
| Full fresh warm | merged incumbent Muta + all 300,350 rows | Training/export complete; selected step 4,693; one verified Mac GGUF copy |
| Full pilot continuation | selected warm-r16-lr5e6 adapter + all 300,350 rows | Training/export complete; one verified Mac GGUF copy; earlier pilot history retained |

The 300,000-row private-exclusion treatment was cancelled by the user; it is
not a finalist or a distribution-licence conclusion. All three current full
treatments use the private 300,350-row artifact in their new stage.

Warm lineages retain the incumbent's earlier licence-clean ARC/QASC MCQ stage.
The fresh warm run starts a new adapter on the already-merged incumbent;
the pilot-continuation run loads the selected pilot adapter exactly once onto
that original parent, resetting optimizer/schedule. No adapter is applied twice.
The pilot's 20,000 prior example exposures are not additional unique rows.

Historical snapshot at **2026-09-19 03:48:40 UTC**:

| Deliverable | State |
|---|---|
| Three full-data trainings / exports / Mac copies | Complete / complete / all three hash-verified, one copy each |
| Five-model normal-stop / duplicate smokes | Passed; 10 responses each |
| Five-model known judges / STEM | All 550 responses complete, validated and semantically reviewed; 2 caps retained |
| Default decision | Retain previous Muta; no full-data promotion; unchanged 20K warm pilot is best challenger |
| Independent battery / target CPU qualification | 0 admitted items / not measured; no universal-winner claim |

The [final result table](results/full-five-gguf-comparison-20260919/README.md)
reports strict MC, semantic MC, explanations, written quality and reviewed
judges separately, without a new composite score. Review is unblinded and
agent-based. All 220 control generation signatures reproduced their historical
outputs; re-adjudication, not model/runtime changes, explains the score revisions.
The default file was not swapped. Oracle inference ended and our lock was
released at 03:47:48 UTC after successful post-run checks.

Fresh-warm's Mac copy was verified at 03:18:50 UTC, SHA256
`75f6a7563ede859aca6c6ddba1625068156e143858c7f841b27ff6208a2b84f3`.
The [frozen five-model manifest](evaluation/full-five-gguf-20260919/candidate-manifest.json)
includes previous Muta and the unchanged best pilot as controls; the
[sealed judges run](evaluation/full-five-gguf-20260919/judges/COMPLETED.json)
and sealed STEM outputs are bound to the final semantic ledgers. Development
loss is not answer quality. All three full stages processed 300,350 rows over
one epoch and 4,693 optimizer steps.
The cancelled CSD3 job received no allocation or training; its authorized Oracle
replacement completed once. Earlier preprocessing and launch observations remain in the
[fresh-warm proof notes](training/full-best-warm-private-enriched/README.md).
See [launch/export status](results/FULL_TRAINING_LAUNCH_STATUS.md) and
[single-copy Mac delivery](../models/round2/full/README.md). The clean export's
original controller failure is preserved alongside its successful, separate
artifact reconciliation; it was not relabelled or re-exported.

## Required final contents

| Path | Evidence |
|---|---|
| `lineage/` | base, incumbent, adapter, merged-checkpoint and GGUF receipts |
| [Dataset proof index](dataset/README.md) | Exact size/source/licence description, private artifact link, six source-bound illustrative rows and separate development manifest |
| `configs/` | preregistered sweep and every resolved run config |
| `scripts/` and source links below | Probe/supervisor helpers plus exact hash-bound training/export sources already in the repository; no duplicate code copies |
| `training/`, `hosts/` | adapters, logs, Trainer state, metrics and loss curves; original full runs remain on GPU hosts |
| `exports/` | merge/quantization manifests, guarded export and reconciliation receipts |
| `evaluation/` | full identical-prompt outputs and score tables |
| [Current practical decision](results/PRACTICAL_WINNER_DECISION.md), [historical known-suite comparison](results/full-five-gguf-comparison-20260919/README.md) | Retain previous Muta; completed fresh-instance comparison, no new model promoted; target-CPU qualification remains unmeasured |

## Executed training and export source index

The local files below were rehashed on 19 September and match the preserved
run/export authorities. Execution used immutable remote snapshots, not live
edits of these local paths; the hash is the identity. Keep these sources in the
final private submission snapshot together with their run receipts. No new
commit or publication is implied by this index.

| Source | SHA256 |
|---|---|
| [Round-two trainer](../model-development/finetune/train_lora_round2.py) | `fd72eaa4e1c2ec86a2494473fe3b6f5be9a95b590f6a04a31f7e48375659ee13` |
| [Training helper](../model-development/finetune/train_lora.py) | `bfca938da9413ef61a12d4c46ee853d74ebf0c7af69749411e000f8c88e06637` |
| [Manifest/lineage verification](../model-development/finetune/campaign_io.py) | `ded88829f91109eb6664d3cf177cde7a8c9665cab731204213ab33047b8fe121` |
| [Full-stage launcher](../model-development/finetune/launch_round2_full.py) | `98f3f5b3586296d5da254962e732ab049cdd557781b9f3df8a946d32763ea14b` |
| [Merge and quantization](../model-development/finetune/merge_and_quantize.py) | `ed215c907a1013b85c1b619f83dc3a3a3f75b193136bff21709e1c80c883e1be` |
| [Frozen full-run config](configs/full-runs-v3.json) | `da828b9146415ca822fecf1961808b914e9666cf7452de34e7704b97f83675da` |

The original clean export controller failure and subsequent reconciliation are
preserved separately. The later corrected controller is not retrospectively
described as the clean attempt's executed source; see the
[correction/reconciliation record](../docs/plans/2026-09-19-export-subprocess-verifier-correction.md).
Exact host commands, conversion tool identities and model hashes belong to each
run's training/export receipts. Some campaign evidence remains untracked until
the eventual submission snapshot; that is distinct from a missing local file.

The full 300,350-row dataset stays private. Any public representative sample
must contain only `muta_verified_stem_v2` or `deepmind_mathematics` records.
The 350 WAEC/Cheetah rows remain labelled private-use/restricted; project-owner
approval is not described as a publisher licence.

Training is performed on SSH/Slurm GPU hosts, not a hosted notebook. Therefore
the notebook-link requirement is not applicable; host receipts and Slurm job
IDs replace it.

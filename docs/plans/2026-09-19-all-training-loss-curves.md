# All retained Muta training loss curves

The user requests the eight pilots, the five compared models and Muta base.
Produce a small local gallery from existing numeric logs without retraining,
reevaluation, copying checkpoints, or changing historical evidence.

## Run accounting

There are twelve distinct training histories: eight 20K pilots, three full-data
stages and the original incumbent Muta. The five-model evaluation roster reuses
the incumbent, the warm-r16-lr5e6 pilot and those three full stages. Show that
mapping explicitly; do not manufacture five additional training runs.
Untouched upstream Qwen has no Muta fine-tuning history. Its upstream training
curve is unavailable here, which is not zero loss and not a missing Muta run.

## Plot and evidence rules

- Read retained metrics.jsonl or original Trainer log_history only. Hash source
  files, record train/evaluation point counts, actual step ranges and selected
  checkpoint when established by the run manifest.
- Plot logged training loss and development evaluation loss with distinct
  labels against optimizer step, with no smoothing, interpolation of missing
  measurements, invented step-zero points or final-summary loss as a step.
- The incumbent original checkpoint-500 trainer_state.json is its training
  history. Do not substitute later recovery evaluation as original training.
- Keep each stage's own step axis; a continuation stage starts a new optimizer
  and schedule. Do not join it to its pilot as one uninterrupted trajectory.
- Prefer an eight-panel pilot overview, a five-panel evaluation-roster overview,
  and an original-Muta detail, with a concise local HTML index and source table.
  Use consistent, legible axes where informative and explicitly qualify that
  datasets and host/runtime conditions differ. Loss is not answer accuracy.
- Generated figures and compact receipts only; retain original files in place.
  No private question text. No publication or deployment change.

## Validation

An independent reviewer checks all twelve numeric traces against originals,
stage/roster accounting, finite values, summary exclusion, source hashes and
figure labels. Root visually inspects the generated figures before delivery.

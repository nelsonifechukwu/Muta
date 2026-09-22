# Untouched Qwen baseline addendum — 19 September 2026

## User request and scope

The user asks for the base comparison alongside the completed five-model table.
The base means Qwen/Qwen2.5-1.5B-Instruct without Muta adapters, not the incumbent
Muta or the 20K pilot. Complete the missing base-only measurements. Preserve
the sealed five-model scores, responses, review ledgers and decision; do not
rerun those five models, retrain, re-export or redownload model weights.

## Evidence and comparison qualification

Reuse the existing historical Q4_K_M control on Oracle only after fresh SHA256,
complete tokenizer/template metadata checks and idle/lock checks. Expected SHA
690da7580eb1a18d4093955e71820897be9c7be3b8afd6c1dff892f00eb80fcf;
recorded source Qwen revision989aa7980e4cf806f80c7fef2b1adb7bc71aa306.
Its historical export lacks complete converter/HF-byte/toolchain binding.
Retain that provenance gap explicitly: this is a matched inference-format
baseline, not proof that all differences isolate fine-tuning alone. Do not
silently relabel the existing BF16 judges outputs or ARC500 aggregate as the
new GGUF measurements. If identity or loader checks fail, stop and diagnose;
do not silently substitute a different artifact.

## Frozen questions and settings

- All2000 exact battery items, SHA33d6db7d36c80279ad079f26bb9ea0c1423547fdd3a799d6c4e2bd93fe153d6d.
- Practical settings match the completed run: same exact server and runtime
  dependencies,8 slots×4096context,1024token cap, temperature0,top_p1,seed3407,
  no prompt cache, thinking disabled, same prompt bytes/order.
- Known judges10/STEM100 use their original full-five runner settings and
  exact prompts. Preserve raw outputs and cap/failure/normal-stop evidence.
- No selective retry, prompt changes, normalization or grading relaxation.
  This baseline is added after viewing the five-model outcomes; disclose that.
- The prior backend transport smoke was accepted as non-bitwise repeatable,
  not duplicate-integrity passed. Retain this qualification. A base-only
  arithmetic load/stop check may be used before full inference; it must not
  become an opportunity to select among baseline runs or change any settings.
- Inspect live GPU processes, sharedlock and existing output roots before
  launching. Acquire existing /tmp/muta-round2-full-uid-1000-gpu-0.lock.
  Never interrupt other work or reopen CSD3/past cancelled jobs.

## Implementation and review

Create separate base-only runner/report adapters; leave every hash-bound
historical source file unchanged. Reuse original backend, inventory, raw-join
verification and strict grader functions where feasible. Freeze and review
new sources/configuration/admission before execution. Any narrowed inherited
transport gate must explicitly bind the existing transport acceptance, exact
original configuration, new baseline roster and newly reviewed source;
never fabricate a new original-smoke pass.

Writer and adversarial reviewer independently verify refusal of mismatched
hashes/settings, incorrect candidate count, incomplete queues and missing or
corrupt raw responses. Use synthetic fixtures, not another model execution.

## Reporting

Append a separate six-row descriptive addendum table with the same four
strata/equal macro and known-suite columns. Grade baseline known written and
judges using the existing rubric with agent review; retain original raw texts
and per-item rationales. Use the same fixed20-question diagnostic selection
for baseline reading if needed, never a cherry-picked favorable sample.

Do not retrofit the original26-contrast confidence procedure or replacement
rule into a preregistered six-model decision. Descriptive differences versus
the frozen five results may be shown, with matched single-realization and
export/transport limitations. If the untouched base outscores Muta, report it
plainly and qualify the earlier recommendation as best among its five tested
contenders; do not preserve a misleading all-model winner claim.

Download only new small response/provenance files once. Keep private training
text private and avoid duplicate GGUF files. Deliver the updated comparison
and exact base identity. Do not recreate the closed recurring follow-up
without a new monitoring request.

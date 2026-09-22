# DeepSeek reasoning contender — explicit user addition

The user explicitly requests adding `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` to fine-tuning experiments. Add a fourth initialization with a fresh LoRA, plus its unchanged control. Do not apply the Muta or historical pilot adapter to this different parent. Preserve the existing three-initialization campaign and exact reviewed sources; no live source is changed.

## Evidence, not a presumed winner

Official model card: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
Official release: https://github.com/deepseek-ai/DeepSeek-R1

Reported MATH-50083.9 and AIME2024 pass@128.9 make it an important maths contender. Reported GPQA-Diamond33.8 does not establish broad science leadership. The official evaluation permits32768 generated tokens and sampled evaluation; those are not Muta's CPU deployment conditions. The comparison quoted by the user mixes incompletely specified checkpoints and protocols. No blanket four-model ranking is adopted.

## Integration before execution

1. Pin the official HF revision, exact weight/config/tokenizer/license identities; download once on Oracle, not another large laptop copy. Preserve acquisition manifest and failures.
2. Inspect its own tokenizer, generation prefix, thinking markers, EOS and multi-turn template behavior. The publisher explicitly says its configurations/tokenizers differ and should be retained. Existing Qwen ChatML masks may not be reused without boundary tests. No silent transfer of Qwen tokenizer or unreviewed reasoning stripping.
3. Train only with verified masking and a separate explicit treatment profile. The same8002 source rows are the proposed starting mixture; exact rendered/tokenized exposure differs and must be receipted. If the assistant-target format requires adapting the data, retain original content and record exact reversible rendering transformations separately. Ordinary worked explanations are not relabelled as DeepSeek-generated reasoning.
4. Preserve unchanged DeepSeek as a control so direct-answer/tutoring SFT can be tested for loss of its original reasoning abilities. Use a fresh rank16/alpha16 LoRA and the matched low-LR pilot budget unless a separately reviewed compatibility constraint requires an explicitly disclosed difference.
5. Run its pilot sequentially on Oracle if CSD3's remaining4GPU-hours are needed by the existing two one-GPU pilots. Do not oversubscribe a device or bypass the shared lock. Estimate additional elapsed time only after measured qualification.

## Fair evaluation

Within each DeepSeek control/tuned pair use the same native template and decoding settings. Report a matched deployment-budget comparison (the same cap on total generated tokens, including reasoning) separately from a longer-budget diagnostic. Do not hide reasoning tokens from cost/latency or count truncated reasoning as a delivered answer. Respect the publisher's recommended sampling settings as a separate declared protocol if they differ from the common greedy test; do not change them after seeing outcomes. No claim of reproducing published benchmark scores under a shorter budget.

The final decision still considers science correctness, mathematical reasoning, tutoring, regressions, delivered final-answer rate and deployment cost. A strong unchanged control may win. No target8GBCPU qualification claim without measurements on appropriate hardware.

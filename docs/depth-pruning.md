# Depth pruning — design notes and campaign record

**Campaign:** shrink `Muta-Tutor-Qwen2.5-1.5B` (28 decoder layers) by 25–40 % of its depth,
heal the cut with the recorded LoRA recipe, and promote the result only if it beats the
published file under the ADTC score on the reference audit image. Spec:
[`docs/plans/2026-09-16-depth-pruning-qwen25-1.5b-spec.md`](plans/2026-09-16-depth-pruning-qwen25-1.5b-spec.md);
plan: [`docs/plans/2026-09-16-depth-pruning-qwen25-1.5b.md`](plans/2026-09-16-depth-pruning-qwen25-1.5b.md);
measurements: `bench/measurements/prune-20260917/`; daily journal entries in `RESULTS.md`
(2026-09-17). Code: `model-development/prune/`.

## The method, and why the choices were made

**Which layers.** Two rankings are computed from one forward pass per calibration row
(`block_influence.py`): ShortGPT **Block Influence** per layer, `BI_i = 1 − mean_t cos(x_i,t,
x_{i+1},t)` over token positions (how much a layer rotates its own input — low BI means the
layer is close to an identity map), and the Gromov-style **n-block angular distance**
`d(i, n) = arccos(cos(x_i, x_{i+n})) / π` averaged over tokens for every start `i` and every
block size `n` we might remove. Two selection policies fall out: `lowest_bi` removes the `n`
layers with the smallest BI wherever they sit, `contiguous` removes the single window of `n`
consecutive layers with the smallest angular distance between its input and its output.
Layers 0, 1 and 27 are never removed (`--protect-first 2 --protect-last 1`).

**Calibration data.** 132 rows sampled (seed 3407, stratified by source) from the
`licensed-hybrid` healing train set — never from any ARC / QASC / OpenBookQA / GSM8K split,
the ARC-Easy-500 set, or the ten Round-1 judge prompts; `calibration.py` refuses any row
whose 8-gram overlap with those prompts exceeds 50 %. 19,304 tokens at ≤ 512 per row. Using
the healing distribution means the layers we judge "redundant" are redundant on the data the
model will be re-taught on, not on generic web text.

**Ranking results.** On the base `Qwen2.5-1.5B-Instruct` (float32, CPU), the three lowest-BI
layers are 25 (0.0394), 26 (0.0404) and 24 (0.0468); on the merged tutor (bfloat16, A100)
the ranking is the same except that layer 15 edges out 24 for third place — the maximum
per-layer |ΔBI| between the two models is 0.0019, i.e. the rank-16 LoRA barely moved the
geometry. The `contiguous` windows selected on the base are `[12–15]` (n=4), `[9–15]` (n=7),
`[8–16]` (n=9), `[8–18]` (n=11); on the tutor they are identical except n=7, where the
minimum moved from start 9 (distance 0.19791 on the tutor) to start 12 (0.19788) — a 3e-5
tie-break. Per the plan, the tutor ranking decided the healed 21L candidate, so the healed
21L file dropped layers `12–18` while the unhealed Stage B floor for 21L had dropped `9–15`.
Both files are recorded (`bi-qwen25-1.5b-instruct-base.json`, `bi-tutor-28L-merged.json`).

**Why unhealed screening came before any GPU work (Stage B).** Removing layers changes only
shapes, so tok/s and peak RSS of a healed file equal those of the unhealed file at the same
depth — healing changes weights, not bytes. The screen therefore gives the *real* speed and
RAM gains for free, plus an accuracy floor, and the exchange-rate arithmetic says whether a
depth can pay for itself before an A100 is touched. It also gave the `contiguous` vs
`lowest_bi` verdict at every depth without training anything.

**Projected vs measured payoff (unhealed, reference audit image on `muta-vm`).** The plan's
projection assumed tok/s ∝ 1/bytes-per-token and RSS falling by 30.5 MB per layer:

| Layers | Projected tok/s | Measured tok/s (contiguous) | Projected peak RSS | Measured peak RSS | Measured ARC-Easy-50 |
|---:|---:|---:|---:|---:|---:|
| 28 (published) | 5.77 | 5.77 | 1099.5 MB | 1099.5 MB | 0.84 |
| 24 | 6.57 | 6.50 | 977 MB | 993.0 MB | 0.76 |
| 21 | 7.32 | 7.10 | 886 MB | 912.3 MB | 0.64 |
| 19 | 7.94 | 7.81 | 825 MB | 855.9 MB | 0.52 |
| 17 | 8.66 | 8.41 | 764 MB | 802.7 MB | 0.48 |

Speed tracked the projection to within 3 %; RSS fell ~15 MB per layer less than projected
(the KV cache, compute buffers and the 131 MB embedding do not shrink with depth). Unhealed
accuracy collapsed far faster than the gains grew.

**The exchange-rate rule.** `bench/score.py`: below the 15 tok/s cap, 1 tok/s = 2.0 S_total
points; 100 MB = 0.29 points; 1 accuracy point = 0.5 points. So the ARC points a depth may
lose and still tie the control is `break_even = (0.30·ΔS_perf + 0.20·ΔS_eff) / 0.50`: 3.5
points at 24L, 6.4 at 21L, 9.6 at 19L, 12.3 at 17L. `shortlist()` keeps a depth only if its
*unhealed* loss is within 2× that number. Every unhealed candidate failed (24L-contiguous
lost 8.0 against a 7.0 ceiling), so the shortlist was empty and the plan's fallback applied:
heal the two shallowest depths with the better policy each — `contiguous` at both 24L (68.16
vs 60.28 unhealed S_total) and 21L (63.59 vs 61.99).

**Rejected alternative: scattered `lowest_bi` removal.** At every depth the scattered set
was faster by 0.05–0.19 tok/s (it removes the same number of layers, so this is noise) but
lost more accuracy than the contiguous window — dramatically so at 24L (0.60 vs 0.76 ARC-50).
Removing the deep layers 24–26 one at a time breaks the final blocks' input distribution;
removing one mid-stack window keeps a single "jump" that the surrounding layers can learn
to bridge. This is why ShortGPT-style single-layer BI is a good *ranking* but a poor
*selection* rule for multi-layer removal.

**Healing (Stage C).** The BF16 source of the published file — the original
`licensed-mcq` r16/500-step run, whose own Q4_K_M export is byte-identical to the published
GGUF (sha256 `a750d00d…`) — was pruned with `prune_hf_layers.py` (delete
`model.layers[i]`, renumber `self_attn.layer_idx`, fix `num_hidden_layers`,
`max_window_layers`, `layer_types`) and healed with the recorded recipe on `licensed-hybrid`
(13,307 tokenised rows): BF16 LoRA rank 16, α 16, q/k/v/o/gate/up/down, completion-only
loss, 1024 context, micro-batch 4 × grad-accum 4, cosine, warmup 5 %, adamw_8bit, seed 3407,
1000 steps, eval every 250, best-eval checkpoint reloaded before the merge. An **unpruned
control** ran the identical recipe so that "more training on hybrid data" is separated from
"fewer layers". Validation loss on hybrid (nats): control 28L 1.500 · healed 24L 1.645 ·
healed 21L 1.801 (lr 5e-5) / 1.891 (lr 2e-5). Every run's best checkpoint was its final step.
The 21L losses exceed the plan's 0.25-nat warning line above the control.

**Export parity.** Every candidate and the control were exported with pinned llama.cpp
**b10175** (`convert_hf_to_gguf.py --outtype f16` → `llama-quantize Q4_K_M`), the same
llama.cpp the reference profiler runs, and each export manifest records `params_count`,
`block_count`, bytes, sha256 and tensor types (F32 / Q4_K / Q6_K). The export is
deterministic: exporting the unpruned tutor twice gave the same sha256 (`1fce28cd…`), and it
differs from the published file (exported by unsloth's bundled b10472) by 160 bytes with the
same parameter count. That re-export, `rebuilt-28L`, is audited as the same-toolchain control
so no candidate is compared against a file that went through a different converter.

**The `parameters_estimate` trap.** The profiler counts parameters from the GGUF tensor
table and fails a submission whose `metadata.json` claim is more than 15 % off. A pruned file
has 46,797,824 fewer parameters per layer (1.216 B at 21L, 1.357 B at 24L), so
`screen_metadata.py` rewrites the claim from the manifest for every candidate; copying the
published `1.54B` would have failed the audit's fraud check on every pruned file.

**KV-cache non-claim.** Fewer layers do shrink the KV cache (1 KiB/token/layer here: ~3.5 MB
at 512 tokens for 7 layers), but that is noise next to the ~30 MB/layer of weights and the
131 MB embedding, and the measured RSS deltas already include it. It is not claimed as a
separate win.

**Where measurements ran.** Score-of-record audits, the accuracy battery and the judge
prompts all ran inside `adtc-profiler:latest` (upstream `ac2e137`, llama.cpp b10175 scalar
build) on GCP `muta-vm`, one at a time; ranking, pruning, healing and export ran on the
user-supplied A100-40GB host. The organisers' Round-1 VM decoded at ≈0.63× `muta-vm`'s
speed, so every S_perf gain quoted here shrinks by that factor on their hardware.

## Build-time gotchas

### llama-quantize --prune-layers cross-check (Task 4, 2026-09-17)

Task 4 built the byte-exact pruning tool (`model-development/prune/prune_gguf_layers.py`)
and tried to cross-check one candidate against upstream llama.cpp's own layer-pruning path,
per plan Step 7:

```
sudo $L/build/bin/llama-quantize --prune-layers 9,10,11,12,13,14,15 \
  ~/adtc-semis/subs/qwen25-1.5b/model/Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf \
  /tmp/xcheck-21L.gguf copy 2
```

(`$L` = `llama.cpp` b10175 built fresh on `muta-vm` for this check; this is
`unhealed-21L-contiguous`'s drop list.)

**Result: refused**, partway through the streaming tensor copy (on `blk.10`, before
pruning logic would even apply, since tensors are validated in original order regardless of
the drop list):

```
ggml_validate_row_data: found nan value at block 32
llama_model_quantize: failed to quantize: tensor 'blk.10.attn_v.weight' has invalid data
llama_quantize: failed to quantize model from '.../Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf'
```

Retrying with `--allow-requantize` added gave the **identical failure**, same tensor, same
line.

**This is not bad tensor data in the published GGUF.** Controller-run evidence: in the same
reference image (`adtc-profiler:latest`, llama.cpp b10175), `llama-cli --check-tensors`
loads the published `Muta-Tutor-Qwen2.5-1.5B-Q4_K_M.gguf` and generates, and does the same
for all eight `unhealed-*.gguf` candidates. The refusal is specific to
`llama-quantize --prune-layers ... copy`'s own row-data validator rejecting this
already-quantized (Q4_K_M) input on its copy/prune path — not a defect in the source model
or in `prune_gguf_layers.py`'s output.

**Verification of record instead** (per the plan's fallback for this exact scenario):

- the synthetic-GGUF round-trip unit test
  (`test_prune_gguf_roundtrip_drops_layers_and_rewrites_block_count` in
  `model-development/prune/test_prune_helpers.py`), and
- the eight load-and-generate checks against all `unhealed-*.gguf` candidates in the
  reference image (Task 4 Step 6 — every candidate loaded and produced text).

### llama-cli non-interactive flag gotcha (reference image, for later tasks)

In this same reference image's `llama-cli` (build `b1-60bccc3`), `-no-cnv` /
`--no-conversation` alone do **not** prevent interactive mode from hanging after a single
`--prompt` turn — it drops into its REPL waiting on stdin, which spins indefinitely (and
burns CPU) when stdin isn't attached, e.g. under `docker run` without `-i`. Add
`-st` (`--single-turn`) to get a clean one-shot run that exits after generating.

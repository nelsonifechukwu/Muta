# Model provenance — what we ship, why that exact file, and what we refused

Companion to `scripts/model_specs.py` (the machine-readable pins) and `models/MANIFEST.json`
(what is actually on disk). This file is the *why*; the specs file is the *what*. TDD T2.

Every pin below was resolved against the live HuggingFace API — repo existence and exact
filename confirmed — not inferred from a model name. `scripts/fetch_models.sh` re-confirms
both at run time and refuses to download anything it cannot re-confirm.

## The pins

| artifact | repo | file | licence | size |
|---|---|---|---|---|
| core | `unsloth/Qwen3.5-4B-GGUF` | `Qwen3.5-4B-Q4_K_M.gguf` | Apache-2.0 | 2.55 GiB |
| mmproj | `unsloth/Qwen3.5-4B-GGUF` | `mmproj-F16.gguf` | Apache-2.0 | 641 MiB |
| asr | `csukuangfj/sherpa-onnx-moonshine-tiny-en-int8` | 4 onnx + tokens | MIT | 118 MiB |
| vad | `istupakov/silero-vad-onnx` | `silero_vad.onnx` | MIT | 2.2 MiB |
| tts | `csukuangfj/vits-piper-en_US-joe-medium` | onnx + json + espeak data | CC0-1.0 | 77 MiB |
| embed | `CompendiumLabs/bge-small-en-v1.5-gguf` | `bge-small-en-v1.5-q8_0.gguf` | MIT | 35 MiB |

Tier B (resolved and recorded, fetched only behind a flag): `ggml-org/Qwen3-ASR-0.6B-GGUF`,
`csukuangfj/kokoro-en-v0_19`, `unsloth/Qwen3.5-0.8B-GGUF`.

Exact commit SHAs live in `models/pins.lock.json`. That file is what makes a rebuild
reproducible — it is committed, the weights are not.

---

## Three findings that change the plan

### 1. The Q8_0 vision projector in TDD §4.2 does not exist

§4.2 budgets a Q8_0 mmproj at 0.5 GiB. **No first-party publisher ships one.** Qwen,
unsloth, bartowski and lmstudio-community all publish BF16 / F16 / F32 only. A Hub-wide
scan of every `Qwen3.5-4B*GGUF` repo found Q8_0 projectors in exactly two categories:

- third-party *derivatives* — `mradermacher/*`, `ZuzeTt/*`, `Jagerfly/*`: abliterated,
  "heretic", and roleplay finetunes. These are a **different model**, and categorically
  unshippable in a tutor for children.
- `prithivMLmods/Qwen3.5-4B-f32-GGUF` — the only Q8_0 projector for *stock* Qwen3.5-4B,
  but a single low-trust uploader with no corroboration, for a file that processes photos
  students take of their own work.

So the fetcher **refuses to substitute**. `--mmproj-precision f16` is an explicit,
recorded acknowledgement that we accepted the 0.626 GiB F16 projector instead.

**Consequence — this is the load-bearing part.** F16 costs +0.13 GiB over the planning
figure, and that is precisely what pushes the resident tier to **3.41 GiB, over the
3.3 GiB acceptance cap by 109 MiB**. `verify_models.sh` fails on it rather than rounding
it away. Against the project exchange rate (1 GB ≈ 1.43 tok/s ≈ 5.7 accuracy points) this
is worth roughly 0.3 points of `S_eff` — small, but it is the kind of drift that is only
cheap while someone is still looking at it.

Options, in the order we should try them:
1. quantize the projector ourselves: `llama-quantize` on `mmproj-F16.gguf` → Q8_0. Costs
   build time, no licence or provenance risk, recovers ~0.3 GiB.
2. accept 3.41 GiB and take the `S_eff` hit.
3. re-open D1 toward a smaller core.

Option 1 is almost certainly right and nobody has done it yet. It is **not** in scope for
T2 — T2 fetches and pins; it does not manufacture artifacts.

### 2. The obvious Piper voice is not redistributable

`en_US-lessac-medium` is the default in nearly every Piper guide, and it is a **licence
trap**: it is trained on the CSTR Blizzard 2013 Lessac corpus under a restrictive research
licence. We redistribute this bundle to third parties on a flash drive (TDD §13), so that
is a ship blocker, not a footnote.

Checked every plausible English medium voice:

| voice | dataset licence | verdict |
|---|---|---|
| lessac | CSTR Blizzard 2013 research licence | **rejected** |
| ryan | CC BY-NC-SA 4.0 | rejected (non-commercial) |
| hfc_female / hfc_male | CC BY-NC-SA 4.0 | rejected (non-commercial) |
| amy / kusal | model card says only "See URL" | rejected (unresolvable) |
| **joe** | **CC0** (NabuCasa voice-datasets) | **chosen** |
| libritts_r | CC BY 4.0 | acceptable fallback (multi-speaker) |
| norman / john / kristin | LibriVox public domain | acceptable fallbacks |

`joe` wins on being an unambiguous public-domain dedication, single-speaker (more
deterministic for a tutor than multi-speaker libritts_r), and smaller (60 MiB vs 75 MiB).

`espeak-ng-data` (~17 MiB) ships with it because the Piper phonemizer needs it at run time
and the target has no network.

### 3. The canonical VAD source has no licence at all

sherpa-onnx documentation points at `csukuangfj/vad` for `silero_vad.onnx`. That repo
ships **no LICENSE file and carries no licence tag**. Silero VAD is MIT upstream and
"everyone knows that" — but TDD §13 requires a *recorded* licence per shipped artifact, and
folklore is not a record.

Pinned `istupakov/silero-vad-onnx` instead: MIT-tagged, ships `LICENSE.txt`, and contains
exactly `silero_vad.onnx`. Same upstream model, different mirror.

The risk in swapping mirrors is that sherpa-onnx might reject that particular export. So
that assumption is **not** assumed — `verify_models.sh` instantiates a real
`VoiceActivityDetector` from the fetched file. Verified passing on 2026-07-24.

---

## The KV table: measurement says the opposite of what §5.2 guessed

`verify_models.sh` writes `bench/kv_metadata.json` from the shipped GGUF, and
`make kv-budget MODEL=models/core/Qwen3.5-4B-Q4_K_M.gguf` regenerates `docs/kv-budget.md`
from it. Planned vs measured:

| | §5.2 worked example | measured (`qwen35`) |
|---|---|---|
| n_layer | 36 | **32** |
| n_kv_head | 8 | **4** |
| head_dim | 128 | **256** |
| elements/token | 73,728 | **65,536** |
| q8_0 per 4096-slot | 306 MiB | **272 MiB** |
| trained context | "≥ 32k" | **262,144** |

The head counts look alarming until you multiply: `4 × 256 = 8 × 128 = 1024`, so the GQA
change cancels exactly. The only real saving is 32 layers instead of 36 — **11% cheaper KV,
nothing more.**

**This kills the promotion note in §5.2.** The TDD says "if measurement shows
head_dim/kv_heads smaller than the example, promote to Classroom-8". Measurement shows the
counts *cancel*, and an 11% saving is nowhere near enough:

| profile | KV | + weights + buffers | vs 4300 MiB cap |
|---|---|---|---|
| **Classroom-6-short (default)** | 816 MiB | 4030 MiB | **fits** |
| Classroom-6 | 1632 MiB | 4846 MiB | over by 546 MiB |
| Classroom-8 | 2176 MiB | 5390 MiB | over by 1090 MiB |
| Solo-demo | 544 MiB | 3758 MiB | fits |

Classroom-6-short stays the default and is the *only* classroom profile that fits. Buying
a bigger profile means spending the D6 ladder (q5_1 takes the 6×4096 row to 1152 MiB, i.e.
4366 MiB — still marginally over), not this measurement.

## Smaller notes

- **embed**: `unsloth/bge-small-en-v1.5-GGUF` has ~40× the downloads but ships **f16 only**
  (63 MiB). TDD §4.8 budgets Q8_0 at ~35 MiB. `CompendiumLabs` is the only repo with the
  requested quant, and it hits 35.1 MiB exactly. Popularity does not override the quant.
- **asr**: measures **118 MiB**, over §4.5's "< 100 MiB". That figure was a `[MEASURE]`
  placeholder; this is the measurement. Budget accordingly.
- **asr-multi**: `ggml-org/Qwen3-ASR-0.6B-GGUF` carries **no licence tag and no LICENSE
  file**; Apache-2.0 is inherited from upstream Qwen and is *unconfirmed for the
  repackage*. It is tier B and not fetched by default, so this is recorded rather than
  blocking — but it must be confirmed before it ever ships. `handy-computer/Qwen3-ASR-0.6B-gguf`
  is apache-2.0-tagged and is the better pin if confirmation fails. Also note its true cost
  is ~0.95 GiB, not 0.75 — it needs an mmproj alongside the weights.
- **draft**: `Qwen3.5-0.8B-Q4_K_M` measures 0.496 GiB against a 0.6 GiB plan. Fetching it
  is not adopting it — TDD §4.4 still requires ≥ 1.43× speedup per GiB spent.
- **Stale HF token**: a cached OAuth token in `~/.cache/huggingface/token` made the Hub
  return 401 on API calls that succeed anonymously. Every pinned repo is public, so the
  fetcher runs anonymous by default (`--use-token` opts back in).
- **`llama-cli` needs `-st`**: the load check in TDD T2 is written as
  `llama-cli -m … -p "2+2=" -n 8 --no-warmup`. That command **never exits** on current
  llama.cpp — chat models default to conversation mode, so it sits at an interactive `>`
  prompt. `-no-cnv` is worse: at stdin EOF it spins printing prompts, and produced **916 MB
  of stdout** here before being killed — an OOM in CI rather than a failure. `-st`
  (single-turn) generates and exits 0. `verify_models.sh` uses `-st` with stdin closed.
- **Stalled downloads**: a multi-GiB fetch can leave a half-open socket that never delivers
  another byte and never errors — observed on the core model. The fetcher sets
  `HF_HUB_DOWNLOAD_TIMEOUT`; recovery is to re-run, which resumes from the `.incomplete`
  blob and still hash-checks.

## Open gates this touches

| gate | status after T2 |
|---|---|
| D1 core quant | `--quant-variants` fetches all three bake-off candidates; undecided |
| D5 premium TTS | Kokoro resolved (Apache-2.0), fetched only with `--with-kokoro` |
| D8 embedding model | bge-small-en-v1.5 Q8_0 pinned as planned |
| §5.2 KV table | **now derivable** — `verify_models.sh` writes `bench/kv_metadata.json` from the shipped GGUF's own metadata; T5 regenerates the slot table from it |

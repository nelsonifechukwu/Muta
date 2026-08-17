# Adversarial review: CJK vocab prune of bitcpm4-8b-tq2_0 (2026-08-17)

Reviewed artefacts
- Script: `/Users/timii/Developer/Muta/muta-iq/opt/scripts/prune_vocab.py` (+ `verify_prune.py`)
- Source: `/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf` (73,448 tokens)
- Output: `/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0-envocab.gguf` (44,416 tokens; same inode as `opt/models/bitcpm4-8b-tq2_0-envocab64.gguf`, sha256 `069621f1…`)
- Engine: `opt/llama.cpp` @ 48d22e2 (+ residency-lite patch, MUTA_STREAM unset), `build-cpu` (NEON, i8mm, REPACK=1, LLAMAFILE=1)

## Verdict: PASS-with-notes

No bug found in the pruning. Every mechanical part of the claim holds and was reproduced independently, including a **bit-exact logits comparison** on the real engine. The notes are about the *scope* of the claim (it is a statement about raw logits/argmax, not about normalized probabilities), one intended-but-visible behaviour change (fullwidth math punctuation now byte-falls-back), and cosmetics.

---

## 1. llama-vocab.cpp: anything id/position-derived?

Read `src/llama-vocab.cpp` (load, SPM tokenizer, byte helpers, special-token cache).

| Item | How llama.cpp derives it | Renumbering-safe? |
|---|---|---|
| `token_to_id` / `id_to_token` | built from the token array; `GGML_ASSERT(id_to_token.size()==token_to_id.size())` needs unique strings | yes — 0 duplicate strings in A and B |
| `linefeed_id` | `byte_to_token('\n')` → string lookup `"<0x0A>"` | yes (A 1099 → B 1082; `token_nl()` string is `<0x0A>` in both) |
| bos/eos/unk/pad | KV `*_token_id` (script remaps: eos 73440→44408, others unchanged), then range-checked against `id_to_token.size()` | yes — `token_eos()` returns `<\|im_end\|>` in both |
| eot/eom/fim/eog auto-detect | iterates `token_to_id` (a `std::map` keyed by **string**) matching `"<\|im_end\|>"` etc. | yes |
| `special_eog_ids` | set of the ids above | yes |
| `cache_special_tokens` | all CONTROL/USER_DEFINED/UNKNOWN ids, `std::sort` by text length (unstable) | yes — 11 control tokens; length ties (`<\|fim_*\|>` ×3) don't overlap textually |
| `cache_token_to_piece` | built after load per id | yes |
| SPM merges (`llm_tokenizer_spm_session`) | candidate = `text_to_token(substring)`; priority = `score`, tie-break `l.left > r.left` (symbol *position*, never token id); `resegment` via `rev_merge` keyed by string; fallback `byte_to_token` by `"<0xXX>"` string | yes |
| byte tokens | detected by type 6 attr; `token_to_byte` parses hex from the string | yes (256 byte tokens kept, ids 1089–1344 → 1072–1327) |
| `n_vocab` | `vocab.n_tokens()` (no `minicpm.vocab_size` KV); `create_tensor({n_embd, n_vocab})` for `token_embd`/`output` | yes — both tensors 44416 rows |
| `tokenizer.ggml.pre`=default, `add_space_prefix` (absent → SPM default true), `add_bos=true` | unchanged KVs | yes |
| `tokenizer.ggml.suppress_tokens` / added-token id arrays | would need remapping — **not present in this file** | n/a (portability caveat, §8) |

Nothing in the SPM path depends on ids or on list order. Renumbering is safe.

## 2. SentencePiece semantics — can removing a piece change non-CJK tokenization?

Argument: an SPM candidate merge is always a substring of the input; every dropped piece contains ≥1 char in the regex ranges; so for input with no such char, no dropped piece can ever be a candidate, and since scores/tie-breaks are unchanged, the merge sequence is identical. For inputs that *do* contain such a char but whose original tokenization used no dropped piece, dropped candidates were never winners, so removing them from the queue cannot reorder the winners either. Verified empirically (§3).

Regex audit (decoded from the script's actual pattern): ranges 3000–303F, 3040–30FF, 3100–312F, 3130–318F, 3190–33FF, 3400–4DBF, 4E00–9FFF, AC00–D7AF, F900–FAFF, FE30–FE4F, FF00–FFEF, 2E80–2FDF, 20000–3FFFF. Arrows (2190–), box drawing (2500–), math operators (2200–), `▁` (2581), U+FFFD, emoji, Yi, PUA are **outside** — verified (`math_unicode`, `box_arrows`, `emoji` tests identical). U+3000 ideographic space and U+301C are **inside**.

Dropped-piece census (29,032 dropped, all decodable UTF-8):
- containing an ASCII letter/digit: **0**
- containing any printable ASCII: 13 (`）\`, `）<`, `>）`, `%）`, `}）`, `）,`, `}\\)（`, …) — all anchored on fullwidth parens
- containing Latin-ext/Greek/Cyrillic: 4 (`×（`, `）×`, `）÷`, `÷（`)
- containing `▁` (word start): 670 (`▁中文`, …)
- with no ideograph/kana/hangul at all (only punct/fullwidth/enclosed): 478 — the ones that matter for English/math: `（ ）＝ ＋ － ／ ％ ［ ］ ＜ ＞ ； ． ＊ ～ ｜ 《 》 【 】 「 」 〈 〉 〔 〕 ㎡ ㎏ ㎜ Ｘ Ｐ Ｓ ￡ ￦` and U+3000.
- under-match: pieces in Yi / kana-ext / hangul-jamo etc. remain (29 kept, e.g. `ꌈ`, `🈁`) — harmless.

Consequence (intended, but visible): any input with those chars now byte-falls-back (never seen in training). Repro on both vocabs:

```
"f（x）= 2"   A: ['<s>','▁f','（','x','）','=','▁','2']
              B: ['<s>','▁f','<0xEF>','<0xBC>','<0x88>','x','<0xEF>','<0xBC>','<0x89>','=','▁','2']
"x＝y＋z－w"  A: 8 tokens (single-char pieces)   B: 14 tokens (byte fallback)
"a　b"        A: ['<s>','▁a','　','b']      B: ['<s>','▁a','<0xE3>','<0x80>','<0x80>','b']
```
Fullwidth `（）＝＋` do occur in math text pasted from CJK-locale sources; the deployment must accept that these degrade.

## 3. Chat template / `<think>` / special tokens

`tokenizer.chat_template` (unchanged) emits `<think>\n\n</think>\n` when `enable_thinking is false`; `<think>`/`</think>` are **not tokens** in either vocab (plain text → `<`,`think`,`>` pieces), so identical. All 11 control tokens kept and moved en bloc (73440–73447 → 44408–44415; `<unk>`,`<s>`,`</s>` at 0,1,2).

Test (llama_cpp 0.3.34 `vocab_only`, both `special=True/False`, `add_bos=True`) — 27 texts × 2: ChatML system/user/assistant, ChatML + `<think>\n\n</think>\n`, tool/execute/fim tokens, HTML-tag tokens (ids 3–51), math unicode, box/arrows, emoji, Yorùbá/latin-ext, Greek/Cyrillic/Arabic/Devanagari/Thai/Hebrew, code, whitespace/CRLF, numbers, smart quotes, `¥£€₦₹`, empty, `" "`, `"\n"`, `<s>hello</s>` → **all identical by string and detokenize identically**. The only diffs are the expected ones where the original itself used a dropped piece (`（）＝＋－`, U+3000, actual CJK). Wave dash `〜` was byte-fallback in the original already (identical).

## 4. The 19 padded-back pieces

ids 52–61 `０–９`, 65 `，`, 66 `。`, 67 `！`, 68 `？`, 69 `、`, 70 `：`, 71 `￥`, 76 `。。。`, 77 `。。。。。。` — all type NORMAL, score 0.0, real rows. Harmless for the identity claim (strictly *helps* it: these are the CJK-punct tokens most likely to be an English-context argmax, e.g. `，` after numerals, so keeping them keeps greedy output identical where dropping would have diverged). Product-wise: the model can still emit `，。！？：`; nothing in the pruned model prevents that any more than the original did. Note `,`/`.` etc. still tokenize identically (`"a，b。c"` identical in both).

## 5. gguf-py writer / header diff

```
A keys 41, B keys 42; KV order identical for common keys; alignment 32/32; 293/293 tensors
ADDED  muta.vocab_prune (STRING)
DIFF   tokenizer.ggml.tokens     ARRAY[STRING]  73448 -> 44416
DIFF   tokenizer.ggml.scores     ARRAY[FLOAT32] 73448 -> 44416   (dtype float32 ✓)
DIFF   tokenizer.ggml.token_type ARRAY[INT32]   73448 -> 44416   (dtype int32 ✓)
DIFF   tokenizer.ggml.eos_token_id UINT32 73440 -> 44408
same   everything else incl. general.file_type=37 (TQ2_0), general.tags, general.languages, chat_template, sampling.top_p/temp, all minicpm.* hparams
Tensors: only token_embd.weight Q4_K [4096,73448]->[4096,44416] and output.weight Q6_K [4096,73448]->[4096,44416] differ in shape;
all 291 other tensors byte-identical (full compare); data offsets monotone, all 32-aligned, file ends exactly at last tensor (no slack).
Kept rows: scores/types identical under the string map; kept-id order monotone; ids 0..51 unchanged, first change at 78 (52..77 padded back).
```
`verify_prune.py` additionally proved kept-row byte identity for both sliced tensors (`np.array_equal(A[map_b], B)`), which I re-derived (2304 B/row Q4_K, 3360 B/row Q6_K).

Repack note: on this host `output.weight` (Q6_K) is repacked to the 8×8 i8mm kernel iff `ne[1] % 8 == 0` (`ggml-cpu/repack.cpp`); 73448 % 8 == 0 and 44416 % 8 == 0, so original and pruned take the *same* kernel. The intermediate 44,397-row file (`prune_tq2_0.log`) would silently have taken the non-repacked path — the `--pad-to 64` fix was necessary, not cosmetic.

## 6. Runtime (under the machine lock, `build-cpu`, MUTA_STREAM unset)

Greedy `llama-completion -n 40 --temp 0 -no-cnv -t 4 --no-warmup --no-display-prompt --simple-io -c 512`, prompts:
1. `The derivative of x^3 is` 2. the crates/naira prompt 3. `Photosynthesis is the process by which` 4. raw ChatML `<|im_start|>user\nSolve for x: 3x - 7 = 11. Show your working.<|im_end|>\n<|im_start|>assistant\n`

→ **all four outputs byte-identical** (md5 A==B: 277e60fa…, c2525f80…, 1543017c…, 5aef5e02…). Decode ~20.6–22.2 t/s both.

Logits (own harness `logits_dump.c` linked against `build-cpu/bin/libllama.dylib`, `parse_special=true`, all positions, prompts 2 and 4):
```
prompt 2: prompt tokens identical by string; max|logitA-logitB| over kept tokens = 0.000e+00, bit-identical: True; argmax identical at all 39 positions
prompt 4: same, 31 positions, bit-identical: True
dropped-token probability mass in the ORIGINAL: mean 1.4% (prompt 2) / 5.1% (prompt 4), max 27.8% (after BOS) / 49.5% (after "<|im_start|>user\n")
```

## 7. Profiler

`adtc_profiler.gguf.extract_metadata`: original `{'architecture':'minicpm','context_length':32768,'params_count':8185254016}`, pruned `{'architecture':'minicpm','context_length':32768,'params_count':7947423872}` (−237.8 M, −2.9 %). `fraud_check("8B", 7947423872)` → within ±15 % → passes. `submission.json` already carries `params_count: 7947423872`.

## 8. Notes (no action strictly required)

1. **Scope of "identical".** Raw logits over kept tokens are bit-identical ⇒ greedy/argmax is identical (proved above). *Normalized* quantities are **not**: the softmax loses the CJK mass (1–5 % on average in English contexts, up to ~50 % right after the ChatML user header). Hence (a) PPL 10.5581 (base) → 10.4753 (pruned) is pure renormalization, not a quality gain — do not quote it as one; (b) lm-eval loglikelihood metrics (arc_easy acc/acc_norm) are only *approximately* preserved — the shift is per-position and continuation-dependent so a choice flip is possible; the reproduced 0.84/50 is empirical evidence, not an identity; (c) any non-greedy sampler — including the GGUF's own defaults `general.sampling.temp=0.8`, `top_p=0.8` that llama-completion picks up — samples from a renormalized distribution, so sampled outputs differ even at a fixed seed.
2. Fullwidth math punctuation `（）＝＋－／％［］` and U+3000 now byte-fall-back (§2). Intended, but document it as a known degradation for pasted CJK-locale math.
3. `general.languages` still `["zh","en"]`; cosmetic, but now inaccurate.
4. `prune_vocab.py` portability (not bugs for this file): only types 3/6 are unconditionally kept (a USER_DEFINED CJK token would be dropped, breaking `cache_special_tokens`); id-bearing arrays such as `tokenizer.ggml.suppress_tokens` / `general.parameter_count` are copied verbatim, not remapped/recomputed. Also `verify_prune.py` hard-codes the four `*_token_id` keys.
5. `verify_prune.py` tokenizes with pip `llama_cpp`'s bundled llama.cpp, not `build-cpu`; my `build-cpu` harness confirmed prompt-token identity there too, so no gap in practice.
6. `with_lock.py` opens the lock file with `"w"` before `flock`, truncating the holder's info line while a waiter is queued (locking itself is correct; only the diagnostic line is lost).

Artefacts of this review (scratchpad): `…/scratchpad/rp/{run_all.sh,logits_dump.c,cmp_logits.py,gen_*_{A,B}.txt,lg{2,4}_{A,B}.bin}`.

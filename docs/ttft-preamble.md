# The TTFT preamble — TinyStories-1M as a warm-up model

**Status:** implemented, **off by default** (`MUTA_RT_TTFT_PREAMBLE=1` to enable).
**Weights:** not cleared for redistribution — see [Licence](#licence-the-blocker-that-decides-shipping).
**Code:** [`runtime/ttft.py`](../runtime/ttft.py) ·
[`orchestrator/gateway/preamble.py`](../orchestrator/gateway/preamble.py) ·
[`scripts/fetch_ttft_model.py`](../scripts/fetch_ttft_model.py)

## The problem

Time-to-first-token on the first turn of a conversation is prefill-bound. Turn 2 onward is
nearly free — `--cache-ram 256` plus `ctx_checkpoints 2` means the system-prompt prefix is
already in the engine's cache — but the first turn pays for the whole system prompt, and on
the 8 GB x86 target that is seconds. A student watching an empty pane reads that as broken,
not as thinking. SC-3 sets the bar at < 2.5 s.

The idea: put a model so small its prefill is free in front of the one whose prefill is not,
and let it write into the dead window.

## Why it is NumPy and not a GGUF

The obvious implementation — hand llama.cpp a second, tiny model — is closed. Four
independent blockers, all verified rather than assumed (2026-08-08):

1. **llama.cpp cannot convert it.** TinyStories-1M is `GPTNeoForCausalLM`
   (`model_type: gpt_neo`). The converter registers `GPTNeoXForCausalLM`
   (`conversion/gptneox.py`) and `GPT2LMHeadModel` (`conversion/gpt2.py`). GPT-Neo — the
   architecture with alternating global/local attention — is in neither. GPT-NeoX is a
   *different* architecture; the name similarity is a trap.
2. **No usable GGUF exists.** The Hub's only candidate, `superlazycoder/TinyStories-1M-ds-GGUF`,
   contains nothing but `.gitattributes`. The one real TinyStories-1M GGUF
   (`RichardErkhov/ivnle_-_tinystories-lay4-hs128-hd2-1M-gguf`) is a *different model* — a
   llama-architecture reimplementation with a Llama-3 vocab — and is equally unlicensed.
3. **It can never be a speculative draft.** Vocab 50257 against Qwen3.5-4B's 248320. This
   is the same wall documented in [`runtime/config.py`](../runtime/config.py) for
   Qwen3-0.6B: `--spec-type draft-simple` requires a shared vocab. A preamble model is not
   a draft model and cannot become one.
4. **A third llama-server would cost more than it saves.** The vision instance already
   shows the price of a second engine process. For 15 MB of weights, an HTTP round-trip to
   a supervised subprocess is larger than the entire computation.

What is left is to run it in-process. At 8 layers of hidden size 64, a decode step is a
handful of 64-wide GEMVs plus one 64×50257 projection — about 3.6 MFLOP. `numpy` is
already a core dependency (`pyproject.toml`), so this adds **no new dependency to the
image**, no engine patch, and nothing to the pinned `b10035` build discipline.

### The two GPT-Neo details a GPT-2 port gets wrong

- **Attention logits are not scaled.** GPT-Neo omits the `1/sqrt(head_dim)` that GPT-2 and
  every llama-family model applies. Scaling flattens the distribution and yields text that
  still looks like English while being subtly wrong — the worst failure mode, because it
  passes a glance. Guarded by `test_attention_logits_are_unscaled`.
- **Half the layers are local.** `attention_layers` alternates `global`/`local`, and a
  local layer sees only the `window_size` (256) tokens ending at the current one. HF builds
  this as `tril ^ tril(-window)`; the port builds it arithmetically as
  `cols <= rows AND cols > rows - window`. Guarded by
  `test_local_attention_window_is_bounded`.

### Fidelity

Validated against `transformers` `GPTNeoForCausalLM` on the same weights (2026-08-08, M2
host): **max |Δlogit| = 8.6e-05** across short prefills, a KV-cached continuation, and a
400-token prompt that exercises the local layers past their window; greedy generation is
**token-identical** for 30 tokens; the tokenizer reproduces HF's ids exactly.

`torch` and `transformers` are *not* backend dependencies — that validation ran on the dev
host. What ships in `runtime/tests/test_ttft.py` is the subset checkable without them
(tokenizer ids pinned as literals, cache-equals-prefill, the window property, the pinned
greedy continuation, determinism, and every degradation path).

### Reading the checkpoint without torch

`load_torch_state_dict` reads torch's zip+pickle format with `numpy` alone: `data.pkl` is
unpickled with a restricted `Unpickler` whose `find_class` returns only tensor-rebuild
functions, dtypes, or `dict` — anything else becomes an object that **raises when called**.
The classic `__reduce__` payload therefore fails loudly instead of executing
(`test_torch_reader_refuses_to_execute_a_reduce`). This matters because the reader is
pointed at a file downloaded from the internet.

Conversion also **drops the `attn.attention.bias` causal masks** — 2048×2048 bool buffers,
33.5 M of the checkpoint's 37.3 M elements. They are ~90% of the 48 MB download and the
runner builds its mask arithmetically. The result is 3,745,984 parameters in 15 MB.

## How it is wired

`with_preamble` ([`orchestrator/gateway/preamble.py`](../orchestrator/gateway/preamble.py))
exploits the one structural fact that makes this cheap: `ChatEngine.stream_events_chat`
returns a generator whose **first** `next()` issues the HTTP request and blocks through the
entire prefill. Everything after arrives at decode speed. So one helper thread makes that
blocking first call while the request thread streams preamble text, and stops the instant
the real event lands. The engine path is not duplicated, reordered, or retried — the same
generator is handed on, positioned exactly where it would have been.

With no writer (disabled, or unprovisioned) `with_preamble` *is* `iter(events)`: the
off path costs nothing and changes nothing, which is what makes the default safe.

### The close-order trap (found during implementation)

Both stream routes end with a `finally` that closes the engine's generator deterministically
so the partial-reply persist runs on the request thread. **The preamble wrapper must be
closed before the engine generator**, and the two closes must stay two closes:

```python
_close_events(streamed)   # joins the helper thread
_close_events(events)     # idempotent; also covers a close during the preamble phase
```

Closing `events` while the helper thread is still inside `next(events)` raises
`ValueError: generator already executing` — CPython refuses to close a generator another
thread is executing. In `/chat/stream` that exception fires *inside a finally*, skipping
the `sessions.release()` that follows it, so **every client disconnect during the prefill
window would permanently leak an admission slot** — and with `n_parallel 2`, two of them
wedge the tutor for the life of the process. The failure needs a disconnect inside a window
that only exists when prefill is slow, which is to say it would have shown up on the target
box and not on the dev host. `test_route_shutdown_order_survives_a_disconnect_mid_prefill`
pins the safe order and `test_closing_the_engine_generator_first_is_the_trap_being_avoided`
reproduces the failure deliberately, so a refactor that tidies the two closes into one has
something that fails.

### The honesty rules

TinyStories-1M was trained on toddler stories. It cannot tutor, and none of this pretends
otherwise. Four separations, each with a test:

| Rule | Where |
|---|---|
| Own SSE key — `{"preamble": …}`, never `delta` | `routes.py`, both stream endpoints |
| Never persisted — cannot reach `ChatEngine`'s store or the self-check | `test_preamble_is_never_persisted_as_the_reply` |
| Never counted — excluded from `completion_tokens`, the tok/s window, and `ttft_s` | `test_metrics_keep_the_two_first_token_numbers_apart` |
| Never styled as speech — muted italic sans, dashed rule, permanent "warming up" tag, **removed from the DOM** on the tutor's first token | `ui/app.js`, `ui/styles.css` |

`done` carries **two** first-token numbers, deliberately unmerged: `ttft_s` is the engine's
own — what the tutor took to speak — and `preamble_ttft_s` is when the pane stopped being
empty. Collapsing them into one figure would be the dishonest version of this feature, and
`preamble_ttft_s` is **not** a `S_perf` input: the scored path is llama-bench against the
submitted GGUF (`docs/rules-digest.md`), which never sees this code.

## Measurements (2026-08-08, M2 Pro dev host, native Python)

| | |
|---|---|
| Load (npz + vocab + merges) | 49 ms |
| First generation after load | 32 ms — **warmed at boot**, see below |
| First chunk, warm | **1.6 ms** (p50), 2.0 ms (p95 of 20) |
| Throughput | ~660 tok/s |
| Resident cost | ~51 MB (15 MB weights + ~36 MB Python tokenizer tables) |
| CPU | **0.99 cores** — single-threaded; `ttft_max_tokens 48` caps it at ~80 ms of one core |

Two consequences worth stating rather than hiding:

- **It briefly competes with the prefill it is waiting for.** ~80 ms of one core, against a
  multi-second prefill that is using all of them. Small, but not zero; lower
  `ttft_max_tokens` if the x86 A/B says it matters.
- **The 51 MB is mostly tokenizer, not model.** The Python `dict` of 50257 vocab entries
  and 50k merge ranks costs more than the weights. Against a 7 GB ceiling that is 0.7%, but
  it is the obvious thing to attack if the budget ever tightens.

Boot warm-up (`PreambleWriter.warmup()`, called from the app lifespan) exists because the
32 ms cold generation would otherwise land on the first student's first turn — the exact
request this feature exists to make feel fast.

## Licence: the blocker that decides shipping

`roneneldan/TinyStories-1M` **declares no licence**: no `license:` tag, no LICENSE file,
nothing in either README. The §13 redistribution policy in
[`scripts/model_specs.py`](../scripts/model_specs.py) is permissive-or-refuse, so this
artifact is deliberately **not** in `ARTIFACTS` — putting it there would mean either
weakening that gate for every model or writing a licence claim that cannot be supported.
It has its own fetcher, which prints the status on every run.

**Before this ships in a bundle**, one of:

1. The upstream licence gets resolved (the dataset is CDLA-Sharing-1.0; the model is silent).
2. The weights get swapped. The runner is architecture-generic GPT-Neo — any `gpt_neo`
   checkpoint drops in by re-pointing `fetch_ttft_model.py`; a GPT-2-architecture model
   needs the fused `c_attn` split and the `1/sqrt(head_dim)` scale reintroduced.
3. The feature ships off, which is the current default.

## What this does not solve

The preamble hides latency; it does not reduce it. The honest TTFT reductions are still
available and independent of this: prewarming each mode's system-prompt prefix into the
engine's cache at boot (first-turn prefill becomes a cache hit), and raising `n_ubatch`
from its memory-driven 128 if the x86 A/B shows prefill gaining more than the compute
buffer costs. Neither has been done.

## Usage

```bash
python scripts/fetch_ttft_model.py     # ~50 MB download -> models/ttft/ (15 MB on disk)
MUTA_RT_TTFT_PREAMBLE=1 ./run.sh       # or set it in docker-compose.yml
```

Knobs, all `MUTA_RT_*` ([`runtime/config.py`](../runtime/config.py)): `TTFT_PREAMBLE`,
`TTFT_MODEL_DIR`, `TTFT_MAX_TOKENS`, `TTFT_TEMPERATURE`, `TTFT_SEED_TEXT`.

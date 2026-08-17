# R5 — Baking behaviour into the GGUF: chat template, thinking switch, sampling metadata

Research date: 2026-08-17 (Gate 1 due 2026-08-25). Team context: ADTC 2026 Laptop LLM track, `math_scientific_reasoning`, team-muta, submission `model/bitcpm4-8b-tq2_0-envocab.gguf` (arch `minicpm`, MiniCPM4.1-8B ternary, ChatML template, `general.sampling.temp=0.8`, `general.sampling.top_p=0.8`, `tokenizer.ggml.add_bos_token=true`, EOS 44408 `<|im_end|>`).

Legend: **[VERIFIED]** = read from primary source (llama.cpp source at the audit tag b10175 or master b10360, installed llama-cpp-python 0.3.34 source, Ollama source, HF repo files) **or reproduced by a test I ran today**; **[INFERRED]** = my reasoning from verified facts; **[SECONDARY]** = third-party doc/paraphrase.

Companion docs: `r2_judging.md` (what judges run — this report goes deeper on the mechanism it recommends), `docs/REPORT.md`.

---

## 0. Executive summary

1. **Yes — the GGUF's `tokenizer.chat_template` is arbitrary Jinja and llama.cpp at the audit tag b10175 executes it with `--jinja` on by default for `llama-server` and `llama-cli`** [VERIFIED, source + tests on a b10175 build]. A template that injects a default system turn when the caller supplies none works exactly as in HF `apply_chat_template`. Since 2026-01-16 (PR #18462) llama.cpp uses its **own Jinja engine (`common/jinja`)**, not minja; b10175 (2026-07-29) and b10360 (master, mid-Aug) share byte-identical `chat.cpp`/`chat-diff-analyzer.cpp` behaviour for our template.
2. **The thinking switch is the subtle part.** llama.cpp *always* defines `enable_thinking` in the template context (default value = "does the differential analyzer think this template supports thinking?" AND `--reasoning` ≠ off). With the stock MiniCPM4.1 template the analyzer says **reasoning = NONE** *only because of the trailing `\n` in `'<think>\n\n</think>\n'`* — so `enable_thinking=false` is passed, the empty think block is rendered and the model answers directly. Removing that newline flips b10175 to **think-by-default** (tested). Meanwhile **llama-cpp-python / HF transformers do not define `enable_thinking`**, so the stock template puts the model in **thinking mode** there. Recipe below is written so every engine defaults to no-think unless the caller passes `enable_thinking=true`.
3. **Recipe (tested on b10175 llama-server + llama-cli, b10360, llama-cpp-python 0.3.34, transformers 4.51.3):** ChatML template that (a) prepends a ~50-token tutoring persona as the system turn when the first message is not `system`, (b) merges (prepends) it when the caller's system message doesn't already contain the persona marker, (c) starts the assistant turn with `<think>\n\n</think>\n` unless `enable_thinking is true`, (d) starts with `{{ bos_token }}` (llama.cpp strips it and lets the tokenizer add BOS; llama-cpp-python/HF then also get a BOS). Bake with `gguf-new-metadata --chat-template-file`; tensor bytes unchanged → S_perf/S_eff unchanged; sha256 changes → update `download_model.sh`/`metadata.json`.
4. **What can defeat it:** `--no-jinja` (legacy path → plain ChatML: persona lost **and** MiniCPM4.1 falls back to thinking mode); `--chat-template chatml`/`--chat-template-file` (operator override); Ollama (`ollama create` matches the GGUF template by Levenshtein < 100 against a fixed list; **even the current MiniCPM4.1 template scores 110 → no match → raw `{{ .Prompt }}`**, i.e. Ollama already ignores our template and would ignore the new one); a judge UI that sends its own system prompt (we merge, not replace — acceptable); a template that fails to parse **kills llama-server at startup** (tested → sandbox crash = DQ; validate before shipping).
5. **Sampling metadata:** `general.sampling.*` (PR #17120, merged 2025-11-25) is honoured by llama-server/llama-cli at b10175 (user flags > GGUF > hardcoded); **not** by llama-cpp-python (create_chat_completion defaults temp 0.2/top_p 0.95/top_k 40/min_p 0.05) nor Ollama. Existing scalar keys can be changed **in place** with `gguf-set-metadata`; new keys (`penalty_repeat`, `min_p`, `top_k`) need a GGUFWriter rewrite (the team's `prune_vocab.py` already does one).
6. **Persona wording is a measured risk, not a free win:** with the R2 wording ("Solve step by step…") at the GGUF's temp 0.8, 1/3 seeds on tp_001 produced a "Step 1/Step 2 skeleton" loop with no answer; the same prompt without persona answered 3/3 (one wrong). Different wording/lower temperature fixed it in my small samples. A/B the final persona + sampling on the audit binary before Gate 1.

---

## 1. Sources and method

| # | Source | How used |
|---|---|---|
| S1 | llama.cpp **b10175** source (tarball `scratchpad/b10175.tar.gz`, byte-identical `common/chat.cpp` and `common/chat-diff-analyzer.cpp` to tag `b10175` = commit `60bccc3`, released 2026-07-29) + local arm64 build `scratchpad/llama-b10175/build/bin/{llama-server,llama-cli}` (CPU only, `-DGGML_METAL=OFF`) | all "audit tag" claims and every `probe_*.log` / `gen_*.log` test |
| S2 | llama.cpp **b10360** (2026-08, `muta-iq/opt/llama.cpp` clone + Homebrew `llama-server` b10360) | "current master" comparison; `git diff b10175..b10360` on `common/jinja`, `common/chat*.cpp`, `tools/server`, `tools/cli`, `tools/ui` |
| S3 | llama-cpp-python 0.3.34 (`~/miniforge3/envs/ai/.../llama_cpp/llama.py`, `llama_chat_format.py`), jinja2 3.1.6, transformers 4.51.3 | Q2; rendering tests |
| S4 | Ollama source (`server/model.go` `detectChatTemplate`, `template/template.go` `Named`, `template/index.json`, fetched today; re-fetched `template.go` from GitHub main) + HF Hub docs `docs/hub/en/ollama` | Q3 |
| S5 | LM Studio docs `lmstudio.ai/docs/app/advanced/prompt-template`; GPT4All docs `chat_templates.html` | Q3 [SECONDARY] |
| S6 | HF repos: `openbmb/MiniCPM4.1-8B` (`tokenizer_config.json`, `generation_config.json`, model card), `Qwen/Qwen2.5-7B-Instruct`, `meta-llama/Llama-3.1-8B-Instruct`, `ibm-granite/granite-3.3-2b-instruct`, `HuggingFaceTB/SmolLM3-3B`, `openbmb/MiniCPM5-1B` chat templates (`scratchpad/r5/tmpl/*.jinja`) | Q4 |
| S7 | llama.cpp PR #18462 (new Jinja engine), PR #17120 (model-embedded sampling params), `common/jinja/README.md` | Q1/Q5 |
| S8 | Our GGUF metadata dump (`gguf.GGUFReader`) | current template/keys |

Test artefacts (all under `/private/tmp/claude-501/-Users-timii-Developer-Muta/87be2b7d-3db1-4a09-b73d-eb31657570f8/scratchpad/r5/`): `probe.sh` (starts a server, greps the analyzer log, hits `/props` and `/apply-template` with 6 message sets), `probe_<label>.log`, `gen.sh`/`gen2.sh` + `gen_<label>.json` (real BitCPM generations on the b10175 build), `tutor_v1..v7*.jinja`, `smollm2_v2baked.gguf` (template baked with `gguf-new-metadata`, served with **no flags** on b10175), `cli_v2*.log`, `bad_*.log`.

Not testable here: the actual profiler Docker image (Docker not running on this Mac); the b10175 build used is arm64 but the template engine/server logic is architecture-independent.

---

## 2. Q1 — llama.cpp's chat-template engine (b10175 and current master)

### 2.1 Which engine, and what it supports [VERIFIED]

- **minja is gone.** `common/minja/` does not exist at b10175; `common/jinja/` does. PR #18462 "Implement new jinja template engine" (ngxson, merged **2026-01-16**) replaced minja; `common/jinja/README.md`: "A Jinja template engine implementation in C++, originally inspired by huggingface.js's jinja package … Input marking: security against special token injection … Minimal primitive types: int, float, bool, string, array, object, none, undefined". Any "known minja limitations" are therefore irrelevant to the audit binary; the *tests* in `tests/test-chat-template.cpp` and `tests/test-jinja.cpp` are the compatibility contract.
- **Lexer defaults match HF:** `common/jinja/lexer.cpp`: `// note: default config for chat template: lstrip_blocks = true, trim_blocks = true`. (llama-cpp-python's `Jinja2ChatFormatter` and HF transformers use the same two options, so whitespace behaviour lines up across engines.)
- **Statements** (parser.cpp): `if/elif/else/endif`, `for … in … [if …]/endfor` with `break`/`continue`, `set`/`endset` (block set), `macro/endmacro`, `call/endcall`, `filter/endfilter`, `generation/endgeneration` (HF's tag, ignored), comments `{# #}`, whitespace control `-`. No `include/extends/import/block`.
- **Built-ins present** (value.cpp string table): `abs capitalize default/d dictsort endswith first float format indent int items join keys last length list lower lstrip map max min namespace range reject rejectattr replace reverse rsplit rstrip safe select selectattr slice sort split startswith string strip sum title tojson(ensure_ascii, indent, separators) trim truncate unique upper values wordcount`, `raise_exception`, `strftime_now`; tests `is defined/undefined/none/true/false/boolean/string/number/integer/float/mapping/iterable/sequence/callable/even/odd/divisibleby/eq/ne/lt/le/gt/ge/in/lower/upper`.
- **Explicitly not implemented** (throw `not_implemented_exception`): `tojson(sort_keys=true)`, `sameas`/`escaped`/`filter` tests, string `join` builtin, `replace` with a count argument, `unique` on arrays, `map` with a filter mapping, `min/max(attribute=…)`, object `join`, array repetition `[1,2]*3`.
- **Input-marking caveats** (README): "Special tokens dynamically constructed from user input will not function as intended, as they are treated as user input. For example: `'<|' + message['role'] + '|>'`." and template-added leading spaces "get tokenized separately". Our ChatML literals are template-originated (`is_input=false`) so `<|im_start|>`/`<|im_end|>` are still parsed as special tokens; the persona text has no special tokens.
- **Runtime leniency:** an embedded template that reads `undefined_var.foo` at request time did **not** error (server answered normally, `prompt_tokens=4`) — attribute access on undefined yields undefined [VERIFIED, `bad_smollm2_badruntime.log`].

### 2.2 Where the template comes from and what happens if it is bad [VERIFIED]

`common/chat.cpp: common_chat_templates_init(model, chat_template_override, …)`:
- With no `--chat-template*` flag: `llama_model_chat_template(model, nullptr)` → GGUF key `tokenizer.chat_template`; then `llama_model_chat_template(model, "tool_use")` → `tokenizer.chat_template.tool_use` (only this variant is used, and only when a request carries `tools`). Other `tokenizer.chat_template.<name>` (e.g. `rag`) are ignored (`common_chat_templates_source`: "unknown template variant").
- `if (default_template_src.empty() || default_template_src == "chatml")` → built-in `CHATML_TEMPLATE_SRC` (plain ChatML, no think block).
- Two source-level string patches for GPT-OSS/Mistral templates; irrelevant to us.
- The template is compiled at load; on parse error: `LOG_ERR("… failed to initialize chat template … please consider disabling jinja via --no-jinja")` and the exception propagates → `server-context.cpp init: "chat template parsing error … exiting due to model loading error"`. **Tested on b10175: a GGUF whose embedded template has a syntax error makes `llama-server` exit before `/health` ever answers** (`bad_smollm2_badparse.log`). Same fate for a template that *renders* fine for normal chats but throws inside the analyzer's probe conversations (`raise_exception` when there is no system message → "Unable to generate parser for this template … exiting due to model loading error", `bad_raise_emb.log`). In the judge sandbox that is "sandbox execution crash → disqualification". **Validate the baked file with the b10175 binary before shipping.**
- `--chat-template`/`--chat-template-file` overrides go through `common_chat_verify_template` first (arg.cpp:881) and refuse to start with "the supplied chat template is not supported" if the sample render fails.

### 2.3 How `llama-server` applies it on `/v1/chat/completions` [VERIFIED, b10175 `tools/server/server-common.cpp` + `common/chat.cpp`]

1. `oaicompat_chat_params_parse`: messages → `common_chat_msg`s; `add_generation_prompt` from body (default `true`); `continue_final_message`/assistant prefill; `reasoning_format` (server default `--reasoning-format auto` = deepseek); `inputs.enable_thinking = opt.enable_thinking` (server-wide default, see 2.4); then **`chat_template_kwargs` from the server (`--chat-template-kwargs`, `--reasoning on|off`, `--reasoning-preserve`) merged with the request's `chat_template_kwargs` object** (request wins per key); `"enable_thinking": true|false` in kwargs overrides `inputs.enable_thinking`; `reasoning_effort: "none"` forces it false.
2. `common_chat_templates_apply` → `common_chat_templates_apply_jinja`: picks `tool_use` variant only if `tools` present; role workaround `developer→system`; if the template's caps say `!supports_system_role` the system message is merged into the first user turn (`workaround::system_message_not_supported`); `extra_context = {datetime: "%b %d %Y", date_string: "%d %b %Y"}` + kwargs; then either a hard-coded specialised handler (Ministral, GPT-OSS, Functionary, Kimi, Cohere2, LFM2, GigaChat, MiniMax, DeepSeek-V3.2, Qwen3-Coder on b10360…) or the **generic differential autoparser** (`autoparser::analyze_template`) — our ChatML template takes the generic path.
3. `common_chat_template_direct_apply_impl` renders with context `{messages, bos_token, eos_token, enable_thinking, tools?, extra_context…}` — **`enable_thinking` is always present** (`{"enable_thinking", inputs.enable_thinking}`), unlike HF where it is undefined unless passed. After rendering: `if (inputs.add_bos && string_starts_with(result, tmpl.bos_token())) result = result.substr(bos.size())` (and same for EOS at the end) — i.e. **a leading `{{ bos_token }}` in the template is stripped when `tokenizer.ggml.add_bos_token=true`, because the tokenizer will add it** (`tokenize_input_prompts(vocab, mctx, prompt, /*add_special*/ true, /*parse_special*/ true)`).
4. Caps (`common/jinja/caps.cpp`) are computed by *rendering probes*: `supports_system_role` = "was `messages[0].content` **used** when messages = [system, user]" — a template that drops the caller's system content would be classified as not supporting system and llama.cpp would then fold the judge's system prompt into the user turn. Our merge design keeps `supports_system_role=true` (`/props` → `chat_template_caps.supports_system_role: true` for v2/v6/v7).
5. `/apply-template` (POST, same body as chat) returns the rendered prompt — the cheapest way to audit a baked template; `/props` returns `chat_template`, `chat_template_caps`, `default_generation_settings`.

### 2.4 The thinking decision, and why the trailing newline is load-bearing [VERIFIED]

`server-context.cpp init`:
```
const bool template_supports_thinking = params_base.use_jinja && common_chat_templates_support_enable_thinking(chat_templates.get());
enable_thinking = params_base.enable_reasoning != 0 && template_supports_thinking;   // --reasoning auto(-1)|on(1)|off(0)
SRV_TRC("chat template, thinking = %d", enable_thinking);
```
`common_chat_templates_support_enable_thinking` renders `[user:test]` with `enable_thinking=true` and returns `params.supports_thinking`, which the autoparser sets iff `reasoning.mode != NONE`. `analyze_reasoning::compare_thinking_enabled` renders the same conversation with `enable_thinking=false` vs `true` and diffs the tails:
```
} else if (right_trimmed.empty() && !diff.left.empty()) {
    if (!left_trimmed.empty() && string_ends_with(comparison->output_A, left_trimmed)) { … end = diff.left; mode = TAG_BASED; }
```
For MiniCPM4.1's `'<think>\n\n</think>\n'`: `diff.left = "<think>\n\n</think>\n"`, `left_trimmed = "<think>\n\n</think>"`, and `output_A` ends with `"</think>\n"` → `string_ends_with(...)` is **false** → no detection → **reasoning_mode: NONE → thinking = 0 → server passes `enable_thinking=false` → template renders the empty think block → no-think.** Measured on b10175 and b10360 with the real GGUF and with SmolLM2:

| template (b10175 unless noted) | `chat template, thinking =` | `reasoning_mode` | default `/apply-template` tail | `chat_template_kwargs {enable_thinking:true}` |
|---|---|---|---|---|
| stock MiniCPM4.1 | 0 | NONE | `assistant\n<think>\n\n</think>\n` | `assistant\n` (thinks) |
| v1 (R2's, unconditional block) | 0 | NONE | `…<think>\n\n</think>\n` | still `<think>\n\n</think>\n` (cannot enable) |
| v2 / v4 / v6 / **v7** (`not (enable_thinking is defined and enable_thinking is true)`) | 0 | NONE | `…<think>\n\n</think>\n` | `assistant\n` (thinks) |
| v3 (= v2 **without** the trailing `\n` after `</think>`) | **1** | **TAG_BASED** (`reasoning_end: '<think>\n\n</think>'` — bogus) | `assistant\n` (**thinks by default**) | — |
| v7 on b10360 (Homebrew) | 0 | NONE | same as b10175 | same |
| v2 with `--reasoning on` or `--chat-template-kwargs '{"enable_thinking":true}'` | 0 | NONE | `assistant\n` (thinks — kwarg route) | — |
| v2 with `--reasoning off` | 0 | NONE | `<think>\n\n</think>\n` | request kwarg `true` still wins |
| v2 with `--no-jinja` | — (legacy) | — | plain ChatML `assistant\n` — **persona lost, and MiniCPM4.1 thinks by default** | ignored |

Consequences: keep the exact string `'<think>\n\n</think>\n'`; do not "tidy" it. Because `enable_thinking` is *always* defined in llama.cpp, the stock condition `enable_thinking is defined and enable_thinking is false` behaves as "no-think unless the server/analyzer flips it", while in HF/llama-cpp-python (undefined) it means "always think". The recipe inverts the test so both worlds default to no-think.

Also visible in the analyzer output: with templates that inject the persona *inside* the loop on `loop.first` (`muta_v1.jinja` style), `user_msg_start` is detected as `<|im_start|>system\n<persona>…<|im_start|>user`; with the Qwen-style `messages[0]` form (v2/v6/v7) it is the correct `<|im_start|>user`. `user_msg_start` only feeds `message_delimiters` used for KV-cache checkpoint spans (`task.tokens.find_message_spans`), so this is cosmetic, but v7's form is cleaner.

### 2.5 Flags and client paths a judge might use [VERIFIED at b10175 `common/arg.cpp`]

| lever | scope | effect on a baked template |
|---|---|---|
| `--jinja` / `--no-jinja` (`LLAMA_ARG_JINJA`) | server, cli, completion, mtmd | default **on** for `llama-server` and `llama-cli` (`common.h: bool use_jinja = true`; only `LLAMA_EXAMPLE_COMPLETION` and `LLAMA_EXAMPLE_MTMD` set it false). `--no-jinja` → `llama_chat_apply_template` legacy C++: `tmpl_contains("<|im_start|>")` → CHATML → persona and think block gone. |
| `--chat-template JINJA_TEMPLATE` / `--chat-template-file FILE` (`LLAMA_ARG_CHAT_TEMPLATE[_FILE]`) | server, cli, completion, mtmd | replaces ours entirely ("default: template taken from model's metadata"); `--chat-template chatml` = built-in ChatML. |
| `-sys/--system-prompt`, `-sysf` | **cli, completion, mtmd, diffusion — NOT server** | llama-cli pushes `{role:system}` first → our template merges persona + their text (tested: `cli_v2_sys.log`, prompt grew 115→121 tokens = persona + `\n\n` + "Answer in French."). llama-server has no system-prompt flag; the built-in web UI's "System Message" setting defaults to `''` (settings-registry, both b10175 and b10360). |
| `-rea/--reasoning on|off|auto` (`LLAMA_ARG_REASONING`) | server, cli, completion | `on` → `default_template_kwargs["enable_thinking"]="true"` → **turns thinking on for v7** (kwarg route); `off` → forced false; default `auto`. |
| `--chat-template-kwargs JSON` | server, cli | arbitrary template variables (e.g. `{"enable_thinking":true}`; deprecated for that key with a warning). |
| `--reasoning-format none|deepseek|deepseek-legacy` (`LLAMA_ARG_THINK`), `--reasoning-budget N`, `--reasoning-budget-message`, `--reasoning-preserve` | server, cli, completion | parsing/budgeting of `<think>` output; irrelevant while no-think. |
| `--skip-chat-parsing` | server, cli, completion | pure content parser; template still applied. |
| `--prefill-assistant/--no-prefill-assistant` | server | last assistant message → continuation; template renders `messages[:-1]`. |
| per-request body | server | `messages` (system role honoured → merge), `chat_template_kwargs`, `reasoning_effort:"none"`, `add_generation_prompt`, `continue_final_message`, sampling fields (override GGUF defaults). |
| built-in web UI (`tools/ui`, both tags) | server | sends **no system message** by default, **no `enable_thinking`** unless the user picks a reasoning effort ("an explicit reasoning choice overrides the server default, DEFAULT sends nothing"), **no temperature** unless set ("Non-overridden params adopt server default") → GGUF defaults apply. It shows a thinking toggle when the template text contains `enable_thinking` (regex detector `chat-template-thinking-detector.ts`); if a judge switches it on they get think mode. |
| `llama-cli` (b10175 = new `tools/cli`, an in-process llama-server client) | cli | same code path as the server (`cli_v2.log`: differential analysis, `chat template, thinking = 0`, streamed `/v1/chat/completions`); no system prompt unless `-sys`. |
| presets (`common/preset.cpp`) | server | INI files / `--models-dir` sidecars, **not** GGUF metadata — no lever for a bare GGUF. |

### 2.6 Sampling defaults and BOS as seen by llama-server [VERIFIED]

- `common/common.cpp: common_init_sampler_from_model(model, params.sampling)` is called in `common_init_from_params`; per key it reads `general.sampling.{sequence,top_k,top_p,min_p,xtc_probability,xtc_threshold,temp,penalty_last_n,penalty_repeat,mirostat,mirostat_tau,mirostat_eta}` **unless the user passed the corresponding flag** (`user_sampling_config` bitmask). `server-schema.cpp:523 params.sampling = params_base.sampling` seeds every request; the request body overrides per field. `/props` on our GGUF: `temperature 0.8, top_p 0.8, top_k 40, min_p 0.05, repeat_penalty 1.0, repeat_last_n 64, n_predict -1` (top_p 0.8 ≠ hardcoded 0.95 ⇒ read from the file).
- BOS: our GGUF `add_bos_token=true`, BOS 1 `<s>`. `tutor_v7.jinja` vs `tutor_v7_bos.jinja` (`{{- bos_token -}}` prefixed) on the real GGUF: `/apply-template` output identical, `prompt_tokens` **76 = 76**, zero "2 BOS tokens" warnings → llama.cpp strips the template BOS and the tokenizer adds exactly one. (On SmolLM2, whose GGUF has `add_bos_token=false` and BOS=`<|im_start|>`, the template BOS is *not* stripped — 73→74 tokens — so this hinges on `add_bos_token=true`, which our file has.)
- EOG set for our file: `EOS 44408 '<|im_end|>'`, `EOT 44408`, `EOG {2 '</s>', 44408}` (`llama-vocab.cpp` also text-matches `<|im_end|>`, `</s>`, `<|end|>`, …). `n_predict=-1` server default → generation ends only on EOG or context — the template must lead the model to emit `<|im_end|>` (observed `finish_reason: stop` in the non-truncated runs).

---

## 3. Q2 — llama-cpp-python 0.3.x (installed 0.3.34, jinja2 3.1.6) [VERIFIED from source + tests]

`llama.py` (constructor, after metadata load):
```python
template_choices = dict((name[10:], template) for name, template in self.metadata.items()
                        if name.startswith("tokenizer.chat_template."))
if "tokenizer.chat_template" in self.metadata:
    template_choices["chat_template.default"] = self.metadata["tokenizer.chat_template"]
for name, template in template_choices.items():
    self._chat_handlers[name] = llama_chat_format.Jinja2ChatFormatter(
        template=template, eos_token=eos_token, bos_token=bos_token, stop_token_ids=[eos_token_id]).to_chat_handler()
if self.chat_format is None and self.chat_handler is None and "chat_template.default" in template_choices:
    chat_format = llama_chat_format.guess_chat_format_from_gguf_metadata(self.metadata)   # exact-match only: chatml / mistral-instruct / llama-3
    if chat_format is not None: self.chat_format = chat_format
    else: self.chat_format = "chat_template.default"
if self.chat_format is None and self.chat_handler is None: self.chat_format = "llama-2"
```
- `guess_chat_format_from_gguf_metadata` only fires on **byte-identical** built-in templates (`CHATML_CHAT_TEMPLATE`, Mistral, Llama-3). MiniCPM4.1's template (extra `enable_thinking` clause) and ours are not identical → **`chat_format = "chat_template.default"` → our Jinja is executed** (verbose log on the real GGUF: `Available chat formats from metadata: chat_template.default` / `Using gguf chat template: {% for message in messages %}…`; captured prompt tokens `[44409, 2881, 5, …, 44408, 39147, 5, 44409, 12715, 5]` = `<|im_start|>user … <|im_end|>\n<|im_start|>assistant\n`).
- `Jinja2ChatFormatter`: `ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True, extensions=[IgnoreGenerationTags, jinja2.ext.loopcontrols])`, `tojson` filter, `strftime_now`, `raise_exception`; render context = `messages, eos_token, bos_token, add_generation_prompt=True, functions, function_call, tools, tool_choice` + `**kwargs` — **`create_chat_completion` passes no template kwargs, so `enable_thinking` is undefined** ⇒ stock MiniCPM4.1 template renders **no** empty think block ⇒ **thinking mode by default in llama-cpp-python** (rendered: `…<|im_start|>assistant\n`); v7 renders `…assistant\n<think>\n\n</think>\n` (no-think) [both VERIFIED by rendering].
- BOS: `ChatFormatterResponse(added_special=True)` → the handler tokenizes with `add_bos=not result.added_special` = **False**, `special=True` — llama-cpp-python never adds BOS for Jinja templates; the captured token list above starts with `<|im_start|>` (no `1`). Putting `{{ bos_token }}` in the template restores BOS there (rendered `'<s><|im_start|>system…'`), and llama.cpp strips it (2.6). MiniCPM's own vLLM instructions ask for `extra_body=dict(add_special_tokens=True)`, i.e. the vendor wants BOS present.
- Sampling: **`general.sampling.*` is not read** (no reference in the package); `create_chat_completion` defaults `temperature=0.2, top_p=0.95, top_k=40, min_p=0.05, repeat_penalty=1.0`.
- The ADTC profiler's accuracy stage (`adtc_profiler/accuracy.py`, see r2) uses `Llama.tokenize`/`create_completion` on raw text — **no chat template, no system prompt** — so nothing here changes Channel A.
- Precedents in the wild: `abetlen/llama-cpp-python#1096` "Use chat_template from gguf metadata" is the issue that introduced this behaviour; a Jinja feature the sandboxed jinja2 lacks (e.g. HF's `{% generation %}`) is handled by the pass-through extension.

---

## 4. Q3 — Ollama, LM Studio, GPT4All, others

### Ollama [VERIFIED from source, fetched today]
`server/model.go`:
```go
func detectChatTemplate(layers []*layerGGML) ([]*layerGGML, error) {
	for _, layer := range layers {
		if s := layer.GGML.KV().ChatTemplate(); s != "" {
			if t, err := template.Named(s); err != nil {
				slog.Debug("template detection", "error", err, "template", s)
			} else { … layer.Status = fmt.Sprintf("using autodetected template %s", t.Name) … }
```
`template/template.go`:
```go
func Named(s string) (*named, error) { … for _, t := range templates { if s := levenshtein.ComputeDistance(s, t.Template); s < score { score = s; template = t } }
	if score < 100 { return template, nil }
	return nil, errors.New("no matching template found") }
var DefaultTemplate, _ = Parse("{{ .Prompt }}")
```
Ollama **never executes Jinja**: it maps `tokenizer.chat_template` to one of its Go templates in `template/index.json` by Levenshtein distance < 100, else no template layer → `{{ .Prompt }}` (roles dropped). Computed distances against index.json: **stock MiniCPM4.1 template 110 → no match**; tutor_v2 565, tutor_v1 469, muta_v1 478 → no match. So an `ollama create -f Modelfile` with `FROM our.gguf` and no `TEMPLATE` already gives a role-less prompt today; the persona cannot reach Ollama users through the GGUF. HF Hub docs (S4): "By default, a template will be selected automatically from a list of commonly used templates. It will be selected based on the built-in `tokenizer.chat_template` metadata stored inside the GGUF file. If your GGUF file doesn't have a built-in template or if you want to customize your chat template, you can create a new file called `template` in the repository. The template must be a Go template, not a Jinja template." — plus optional `system` and `params` files. Ollama also ignores `general.sampling.*` (Modelfile `PARAMETER` only; defaults temp 0.8/top_p 0.9/top_k 40/repeat_penalty 1.1 [SECONDARY]). Judges are told "llama.cpp only", so Ollama is a low-probability path; if we ever publish for Ollama, ship a Modelfile with `TEMPLATE` (ChatML Go template with `{{ if .System }}`), `SYSTEM "<persona>"`, `PARAMETER stop <|im_end|>`.

### LM Studio [SECONDARY]
Docs: "By default, LM Studio will automatically configure the prompt template based on the model file's metadata." / "You can express the prompt template in Jinja. Jinja is a templating engine used to encode the prompt template in several popular LLM model file formats." / override in "My Models → gear → Prompt → Prompt template", or manual prefix/suffix mode. LM Studio's Jinja engine (huggingface.js-derived) is known to choke on some newer templates (Qwen3.5/GLM threads on HF); ours uses only basic constructs. LM Studio's default system prompt is empty; a per-model default system prompt can be set by the user. Not tested here.

### GPT4All [SECONDARY]
v3.5+ uses Jinja chat templates taken from the GGUF (`tokenizer.chat_template`) with its own engine (originally minja); docs: "The authoritative source for a model's chat template is the HuggingFace repo that the original (non-GGUF) model came from." System message is user-configurable text; not tested.

### Others (brief, [INFERRED] from architecture)
`llama-swap`, Jan, LibreChat/Open WebUI → they front `llama-server` → our template applies unless the front-end injects its own system prompt (Open WebUI: none by default). text-generation-webui's llama.cpp loader renders the GGUF template with Python jinja2 → same as HF (`enable_thinking` undefined → v7 no-think). koboldcpp uses its own adapter files, not the GGUF template.

---

## 5. Q4 — Precedents: templates that inject a default system message [VERIFIED, files in `scratchpad/r5/tmpl/`]

**Qwen2.5-7B-Instruct** — the canonical "default persona when none given":
```jinja
{%- if messages[0]['role'] == 'system' %}
    {{- '<|im_start|>system\n' + messages[0]['content'] + '<|im_end|>\n' }}
{%- else %}
    {{- '<|im_start|>system\nYou are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>\n' }}
{%- endif %}
```
(and, in the tools branch, `{%- if messages[0]['role'] == 'system' %}{{- messages[0]['content'] }}{%- else %}{{- 'You are Qwen, created by Alibaba Cloud. You are a helpful assistant.' }}{%- endif %}` before the `# Tools` block). This is the template the AgriDoc team (r2 §S15) found was the source of the "I am Qwen" identity leak and replaced with their persona — the same mechanism we use.

**Llama-3.1-8B-Instruct** — always emits a system header and injects dates:
```jinja
{{- bos_token }}
{%- if not date_string is defined %}
    {%- set date_string = "26 Jul 2024" %}
{%- endif %}
{%- if messages[0]['role'] == 'system' %}
    {%- set system_message = messages[0]['content']|trim %}
    {%- set messages = messages[1:] %}
{%- else %}
    {%- set system_message = "" %}
{%- endif %}
{{- "<|start_header_id|>system<|end_header_id|>\n\n" }}
{{- "Cutting Knowledge Date: December 2023\n" }}
{{- "Today Date: " + date_string + "\n\n" }}
```
(llama.cpp supplies `date_string`/`datetime` in `common_chat_extra_context`, so the injected date is live.)

**Granite-3.3-2B-Instruct** — default identity + `strftime_now`:
```jinja
{%- if messages[0]['role'] == 'system' %}
     {%- set system_message = messages[0]['content'] %}
     {%- set loop_messages = messages[1:] %}
 {%- else %}
     {%- set system_message = "Knowledge Cutoff Date: April 2024. Today's Date: " + strftime_now('%B %d, %Y') + ". You are Granite, developed by IBM." %}
     …
     {%- else %}
         {%- set system_message = system_message + " You are a helpful AI assistant." %}
```

**SmolLM3-3B** — always writes a system block *and* handles the thinking switch inside it (`enable_thinking` default true, `/think` `/no_think` markers, `## Metadata … Reasoning Mode: …`, `## Custom Instructions`) — an example of a template that *merges* the caller's system text into a house-owned system block, and the case the llama.cpp analyzer comments on ("SmolLM3 changes the system message when enable_thinking flips").

**MiniCPM5-1B (OpenBMB, 2026)** — starts with `{{- bos_token }}`, only emits a system turn if the caller gave one, uses `namespace(...)` and `tojson(ensure_ascii=False)` — evidence that OpenBMB itself now ships templates with a leading `bos_token` for this tokenizer family.

**gpt-oss** ([SECONDARY], well known) injects "You are ChatGPT, a large language model trained by OpenAI. Knowledge cutoff… Reasoning: medium" as a default system block; llama.cpp handles it with a dedicated handler.

Design lesson from these: the robust idiom is *test `messages[0]['role'] == 'system'`, render your header, then loop from index 1* (Qwen/Llama/Granite) — not "inject inside the loop on `loop.first`".

---

## 6. Q5 — Other GGUF-metadata levers that shape generation

| key | who honours it | notes |
|---|---|---|
| `general.sampling.{temp,top_p,top_k,min_p,penalty_repeat,penalty_last_n,xtc_*,mirostat*,sequence}` | **llama.cpp** llama-server/llama-cli/llama-completion since PR #17120 (2025-11-25) — b10175 ✔; precedence user flag > GGUF > hardcoded [VERIFIED]. **Not** llama-cpp-python, **not** Ollama [VERIFIED]; LM Studio/GPT4All: no evidence they read it [INFERRED no]. | Written by `convert_hf_to_gguf.py` from `generation_config.json` (`temperature`, `top_p`, `top_k`, `min_p`, … — HF's `repetition_penalty` is *not* mapped) or `--metadata metadata.json`. Ours: 0.8/0.8 = MiniCPM4.1 `generation_config.json`; the model card instead says "It is advisable to use temperature=0.9, topp=0.95". Change existing keys **in place**: `gguf-set-metadata model.gguf general.sampling.temp 0.5 --force` (scalar, same type; no copy). Add missing keys (`penalty_repeat`, `min_p`, `top_k`) → GGUFWriter rewrite (`prune_vocab.py`-style copy; `GGUFWriter.add_sampling_*` helpers exist). Only affects the judged chat, not the profiler benchmark. |
| `tokenizer.chat_template` | llama.cpp (jinja), llama-cpp-python, LM Studio, GPT4All, HF-style loaders; Ollama only as a fingerprint | rewrite with `gguf-new-metadata in.gguf out.gguf --chat-template-file t.jinja` (full copy; tensor bytes unchanged). |
| `tokenizer.chat_template.<name>` (+ `tokenizer.chat_templates` array) | llama.cpp uses only `tool_use` (when `tools` present); llama-cpp-python exposes each as a selectable `chat_format` but auto-picks `default`; Ollama ignores | `gguf-new-metadata --chat-template '[{"name":"default","template":…},{"name":"tool_use",…}]'` writes them. Not useful for a plain chat model. |
| `tokenizer.ggml.add_bos_token` / `bos_token_id` | llama.cpp tokenizer (`add_special=true` in server) + template BOS stripping; llama-cpp-python's Jinja path ignores it | ours `true`/1 — keep; put `{{ bos_token }}` in the template for cross-engine parity. |
| `tokenizer.ggml.eos_token_id`, `eot_token_id`, `eom_token_id`, `add_eos_token` | EOG set = eos ∪ eot ∪ eom ∪ text-matched control tokens (`<|im_end|>`, `</s>`, `<|end|>`, …) | ours EOG {2, 44408} — correct for ChatML; nothing to change. |
| `general.name` / `general.description` | llama.cpp: printed in `print_info` logs only — **not** in `/props`, `/v1/models` (`id` = filename or `--alias`) or the web UI at b10175 [VERIFIED]; llama-cpp-python: `metadata` dict only | cosmetic; harmless to set to the tutor identity for `gguf-dump`/HF viewers. (r2 §7.3 slightly overstates its visibility.) |
| `minicpm.context_length` (32768) | server `n_ctx=0` → trained ctx → KV allocation | leave (longrope factors keyed to it); ≈1 GiB KV at 32k f16 for our shapes (r2). |
| `general.languages`, `general.tags`, `general.license` | HF/gguf-dump display | keep honest. |

---

## 7. Deliverable — the recipe (tested) and its risks

### 7.1 Template `tutor_v7.jinja` (with BOS line = `tutor_v7_bos.jinja`) — recommended

```jinja
{{- bos_token -}}
{#- Muta tutor template: ChatML (MiniCPM4.1) + default tutoring persona + no-think unless caller asks -#}
{%- set persona = "You are Muta, a friendly mathematics and science tutor for secondary-school students in Africa. Explain clearly in plain English, show the working, state units, give the final answer, and finish with one short check-your-understanding question." -%}
{%- set has_system = messages | length > 0 and messages[0]['role'] == 'system' -%}
{%- if has_system -%}
    {%- set sys_text = messages[0]['content'] | string -%}
    {%- if 'You are Muta' in sys_text -%}
        {{- '<|im_start|>system\n' + sys_text + '<|im_end|>\n' -}}
    {%- else -%}
        {{- '<|im_start|>system\n' + persona + '\n\n' + sys_text + '<|im_end|>\n' -}}
    {%- endif -%}
{%- else -%}
    {{- '<|im_start|>system\n' + persona + '<|im_end|>\n' -}}
{%- endif -%}
{%- for message in messages -%}
    {%- if not (loop.first and message['role'] == 'system') -%}
        {{- '<|im_start|>' + message['role'] + '\n' + (message['content'] | string) + '<|im_end|>\n' -}}
    {%- endif -%}
{%- endfor -%}
{%- if add_generation_prompt -%}
    {{- '<|im_start|>assistant\n' -}}
    {%- if not (enable_thinking is defined and enable_thinking is true) -%}
        {{- '<think>\n\n</think>\n' -}}
    {%- endif -%}
{%- endif -%}
```
Persona text is a placeholder to be A/B-tested (see 7.4); the marker `'You are Muta'` must stay a substring of whatever persona ships (it is the "our own app already sent the persona → don't double it" guard).

Verified behaviour (b10175 server via `--chat-template-file` on the real GGUF and via **embedded metadata with zero flags** on SmolLM2; b10175 llama-cli; b10360; llama-cpp-python 0.3.34; transformers 4.51.3):
- no system → `<|im_start|>system\n<persona><|im_end|>\n<|im_start|>user\n…<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n`
- system "You are a helpful assistant." → `system\n<persona>\n\nYou are a helpful assistant.<|im_end|>…` (merge; `supports_system_role: true`)
- system already containing "You are Muta…" → used verbatim (no doubling)
- multi-turn → persona once at top, turns unchanged
- `chat_template_kwargs {"enable_thinking": true}` / `--reasoning on` / `--chat-template-kwargs '{"enable_thinking":true}'` → block omitted (thinking on); `enable_thinking:false`, `reasoning_effort:"none"`, `--reasoning off`, default → block present (no-think)
- llama.cpp analyzer: `reasoning_mode: NONE`, `chat template, thinking = 0`, `user_msg_start: <|im_start|>user`, `assistant_msg_start: <|im_start|>assistant`; empty `messages` handled (`messages | length > 0` short-circuits in both engines)
- BOS: exactly one (`prompt_tokens` 76 with and without the BOS line on b10175); llama-cpp-python renders `<s><|im_start|>system…`
- persona cost: 50 tokens (v7 wording) with the real tokenizer; ChatML scaffold + empty think block ≈ 26 tokens; llama-server's prompt cache reuses the identical prefix across requests in a slot, so the persona is prefilled once per slot, not per turn.

### 7.2 Bake, verify, ship

```bash
# 1. write template (keep the exact '<think>\n\n</think>\n' string)
# 2. rewrite metadata only (tensor bytes copied → S_perf/S_eff identical; sha256 changes)
gguf-new-metadata model/bitcpm4-8b-tq2_0-envocab.gguf model/bitcpm4-8b-tq2_0-envocab-muta.gguf \
    --chat-template-file opt/templates/tutor_v7_bos.jinja \
    --general-name "Muta Tutor (BitCPM4-8B, English-scoped)" --force
# (optional, in place, existing scalar keys only) gguf-set-metadata model/...-muta.gguf general.sampling.temp 0.5 --force
# 3. validate on the AUDIT tag binary — a parse/probe failure here == sandbox crash == DQ
scratchpad/llama-b10175/build/bin/llama-server -m model/...-muta.gguf --port 8080 &        # NO other flags
curl -s localhost:8080/props | jq '.chat_template, .chat_template_caps, .default_generation_settings.params.temperature'
curl -s localhost:8080/apply-template -d '{"messages":[{"role":"user","content":"Q"}]}'
curl -s localhost:8080/apply-template -d '{"messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"Q"}]}'
grep -E "chat template, thinking = |reasoning_mode:" server.log     # expect 0 / NONE
# 4. real chats: tp_001, tp_002, ~10 guessed hidden prompts, multi-turn follow-ups; no system, no sampling overrides; also once with the web UI
# 5. python: Llama(path, verbose=True).create_chat_completion(...) → confirm 'Using gguf chat template' + prompt starts with <s><|im_start|>system
# 6. re-run adtc-profiler participant mode (accuracy stage unaffected, but sha256/paths in submission must match), update download_model.sh + metadata.json
```

### 7.3 Risks and mitigations

| risk | severity | mitigation / status |
|---|---|---|
| **Template parse or probe-render failure → llama-server exits at load** | DQ | validated on b10175 (7.2 step 3); avoid `raise_exception`, avoid indexing `messages[0]` without the length guard, avoid None concatenation (`\| string`), avoid not-implemented filters (2.1). |
| **Double system prompt** (judge UI / `-sys` / our own app sends one) | low | merge design: persona + `\n\n` + theirs; own persona detected by marker; `supports_system_role` stays true so llama.cpp doesn't fold system into user. If a judge's system prompt contradicts the persona (e.g. "You are a general assistant"), the persona still leads — acceptable in our domain. |
| **Thinking flips on** | medium | only via explicit `enable_thinking=true` / `--reasoning on` / web-UI reasoning toggle (template mentions `enable_thinking` so the toggle appears; default sends nothing). If it does flip on, our analyzer status is NONE so llama-server will not split `<think>` into `reasoning_content` — the raw tags appear in `content`. Alternative "version-proof" variant = v1 (unconditional block, no `enable_thinking` in the template → no toggle, no way to think); trade-off = lose the vendor-standard switch. Since the audit binary is pinned to b10175 where v7 is verified, prefer v7; re-verify if the pin changes. |
| **Trailing-newline fragility** (`'<think>\n\n</think>'` without `\n` → think-by-default on b10175, tested) | high if edited | keep the exact string; add a CI check that greps `<think>\n\n</think>\n` and that `thinking = 0` on the b10175 binary. |
| `--no-jinja` / `--chat-template chatml` / `llama-completion -cnv` | low probability | persona lost **and** MiniCPM4.1 thinks by default (no empty block) — think traces at single-digit tok/s on the audit box. Nothing to do inside the GGUF; document in REPORT.md. |
| Ollama / non-Jinja tools | low (rules say llama.cpp) | already broken for the stock template (distance 110); if publishing for Ollama, ship a Modelfile (`TEMPLATE`, `SYSTEM`, `PARAMETER stop`). |
| **Persona wording changes behaviour** (see 7.4: "Solve step by step…" → 1/3 skeleton loop at temp 0.8) | medium | A/B ≥ 5 seeds × ≥ 10 prompts per wording on the b10175 build at the shipped sampling; prefer wording that names *what to output* over "step by step"; consider `general.sampling.temp` 0.5–0.6 and `penalty_repeat` 1.05/`penalty_last_n` 64 (measure). |
| Prompt-token cost on the no-AVX 4-vCPU box | low | 50-token persona ≈ one prefill batch; cached per slot; keep ≤ ~60 tokens. |
| Channel A (profiler MC benchmark) | none | raw-text loglikelihood path bypasses templates and sampling metadata (r2). |
| Identity/`general.name` | none | not surfaced by llama-server at b10175; set anyway. |
| sha256 / provenance | process | new file → new hash in `download_model.sh`, `metadata.json`, `RESULTS.md`; keep the un-baked file for the profiler comparison. |

### 7.4 Generation evidence (b10175 build, real GGUF, GGUF sampling defaults unless noted, `max_tokens` 400/600, no system message) [VERIFIED, `gen_*.json`]

| template / setting | tp_001 (18000 naira, 24 crates, 25 %) — 3 seeds | notes |
|---|---|---|
| stock MiniCPM4.1 (no persona) | stop/stop/stop, 218/316/291 tok, **937.5 in 2/3** (seed 123 wrong) | plain solutions |
| v2 persona ("Solve step by step, state the final answer clearly, and end with one short check-your-understanding question.") | **length(loop)**/stop/length, 937.5 in 2/3 | seed 42: "### Step 1: Calculate the total cost price… ### Step 2:…" formula skeleton repeated to the token limit, never computes |
| v2 persona, `--temp 0.3` | length/stop/stop, 937.5 in 3/3 | verbose but correct; length cut was verbosity (check section) |
| v5 persona ("Explain clearly in plain English, show the working, state units, give the final answer, and finish with one short check-your-understanding question.") | stop/length/length, 937.5 in 3/3 | one run leaked think-style monologue into content ("Hmm, that doesn't add up. Let me double-check…") — no-think mode still reasons in the open |
| v2 persona + system "You are a helpful assistant." (600 tok) | stop, 445 tok, correct, ends with a check question | merge path behaves |
| v2 persona, tp_002 (falling balls) | 600-tok cutoff (verbose), physically mostly right, ends with "### Check-Your-Understanding Question" | persona instructions are followed |

Take-away: the mechanism works on the audit binary; the *content* of the persona and the sampling keys need the A/B in 7.3 (small samples above are indicative only).

---

## 8. Open questions

1. What exactly is the judges' "in-browser interface" — llama.cpp's web UI, or a custom page? (Determines whether a thinking toggle / system-message box is even visible to them.) Unpublished; ask on Discord/e-mail.
2. Whether the sandbox passes any llama-server flags (`-c`, `--reasoning`, `--chat-template`) — unpublished. Everything above assumes stock flags, which is the only thing consistent with "your exact submission … we run llama.cpp".
3. Final persona wording and `general.sampling.*` values — needs the A/B in 7.3 (not a research question).

# runtime — inference layer (Lane A)

Provisions the model, runs the llama.cpp engine, and holds multi-turn conversations with
persistent memory. The gateway's `/v1/chat` drives it; nothing else talks to llama.cpp
directly (ROADMAP A.2).

## Pieces

| Module | Role |
|---|---|
| `config.py` | `RuntimeConfig` — all knobs, overridable via `MUTA_RT_*` env vars |
| `models.py` | `resolve_model()` — local folder (default) → HF download fallback → **local GGUF path** |
| `server.py` | `LlamaServer` — locate the `llama-server` binary, launch, health-check, `ensure()` |
| `client.py` | `InferenceClient` — HTTP to llama-server `/v1/chat/completions` (blocking + streaming) |
| `memory.py` | `ConversationStore` — SQLite conversations + messages |
| `chat.py` | `ChatEngine` — replay history → call model → persist (the multi-turn loop) |
| `cli.py` | interactive REPL (`make chat`) |
| `run.sh` | shell launcher (`python -m runtime.server`) |

## Model resolution

Default source of record is the **local folder** `models/`. If the file is missing and
`auto_download` is on (default), it is pulled once from Hugging Face and cached there.
Resolution always returns a **local path** — the deploy target is offline (ROADMAP A.1), so
run time never depends on the network. Defaults (override with `MUTA_RT_*`):

```
model_dir  = models/
model_file = Qwen3-0.6B-Q4_K_M.gguf
hf_repo    = unsloth/Qwen3-0.6B-GGUF     # Unsloth Dynamic 2.0 (ROADMAP 15/18 Jul)
hf_file    = Qwen3-0.6B-Q4_K_M.gguf
base_repo  = Qwen/Qwen3-0.6B             # provenance (safetensors source)
```

## The `llama-server` binary

Not vendored. Found in this order: `MUTA_RT_LLAMA_SERVER_BIN` → `runtime/build/bin/llama-server`
(the container/native build, ROADMAP 15 Jul) → `llama-server` on `PATH`.

- **macOS dev:** `brew install llama.cpp`
- **linux/amd64 target:** built in the container into `runtime/build/bin` (Phase 1)

## Run it

```bash
make model     # one-time: download Qwen3-0.6B Q4_K_M into models/  (or let `serve` auto-pull)
make serve     # launch llama-server on 127.0.0.1:8080
make chat      # interactive multi-turn REPL (auto-starts a server if none is up)

./runtime/run.sh --print-cmd   # show the exact llama-server invocation
```

Full-stack path: `make serve` (llama-server) + `make dev` (gateway) → `POST /v1/chat` with a
`conversation_id` for memory across turns. Conversations persist in `data/muta.sqlite3`.

## Notes

- **Qwen3 is a hybrid-reasoning model.** Thinking is off by default (`enable_thinking=false`,
  sent as `chat_template_kwargs` and honoured because the server runs with `--jinja`) so
  tutoring replies stay concise. Set `MUTA_RT_ENABLE_THINKING=true` to see `<think>` traces.
- **CPU-only by default** (`n_gpu_layers=0`) to match the target; raise `MUTA_RT_N_GPU_LAYERS`
  for faster local dev on a GPU/Metal box.
- Benchmarks come from the x86 target box, never here (ROADMAP A.4).

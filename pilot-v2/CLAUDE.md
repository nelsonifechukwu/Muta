# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Muta_v2 is a ground-up restart of **Muta**: an offline, adaptive AI tutor for math and scientific reasoning, built for the ADTC 2026 competition. The deployment target is an 8 GB DDR4 laptop (i5 10th–12th gen / Ryzen 5, integrated graphics only, 256 GB SSD, Ubuntu 22.04 — no GPU), so everything is designed around a small quantized model plus retrieval and verified tool calls, scored on accuracy (50%), tokens/sec (30%), and peak-RAM efficiency (20%) with a thermal penalty.

The full v1 project lives in the sibling directory `../Muta` (README, ROADMAP, bench harness, corpus tooling). Consult it for design context, but this repo is a fresh start — do not assume v1's structure carries over.

## Current state (as of first commit)

The repo has **no commits yet** and very little source. Know these facts before working:

- `llama.cpp/` is a **plain nested clone** of ggml-org/llama.cpp (not a submodule, not gitignored). It is unbuilt. If it should be tracked, convert it to a submodule or add it to `.gitignore` — do not accidentally commit the whole tree.
- `models/` holds downloaded GGUF weights (`Qwen3.5-4B-Q4_K_M.gguf`, `SmolLM2-135M-Instruct-Q4_K_M.gguf`). Weights are gitignored; only `models/MANIFEST.json`, `models/pins.lock.json`, and `models/LICENSES/` are meant to be committed (they don't exist yet — they are the reproducibility/provenance deliverable, so create them when adding models).
- The `.venv` contains an **editable install of v1's `muta` package pointing at `../Muta`** — `import muta` resolves to v1 code, not anything in this repo. Uninstall or reinstall it if v2 grows its own package.

## Commands

Python 3.12 virtualenv at `.venv` (torch, transformers, fastapi, pytest, hypothesis installed).

```bash
source .venv/bin/activate

# Tests (pytest is configured in pyproject.toml: pythonpath=".", testpaths=["tests"])
pytest                          # all tests (tests/ doesn't exist yet)
pytest tests/test_x.py::test_y  # single test

# Build llama.cpp (CPU-only Release build matches the deployment target)
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build -j
```

## Intended layout (encoded in .gitignore)

The `.gitignore` documents the planned architecture even though most directories don't exist yet:

- `corpus/raw/` — licensed past-paper PDFs (WAEC/JAMB etc.); **never committed**, provenance tracked in `corpus/sources.md`.
- `data/` — runtime state: faiss index, sqlite learning twins, caches, engine logs. Regenerable from manifests.
- `runtime/build/` — compiled/downloaded llama.cpp binaries.
- `bench/` — ADTC benchmark harness. The official ADTC profiler is **GPL-3.0 and must never be vendored**: it gets its own isolated venv (`bench/.venv-profiler/`) and is re-cloned by SHA rather than committed (`bench/adtc-profiler/`).
- `certs/`, `keys/` — generated TLS certs and release-signing keys, never committed.

`.gitignore` has no inline comments — keep comments on their own lines (noted in the file itself).

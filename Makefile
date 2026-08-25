# Muta — developer entrypoints. `make help` lists everything.
# The stack itself is compose-first: `./run.sh` (or `make up`) brings up db+backend+frontend.
.DEFAULT_GOAL := help
PY ?= python3

.PHONY: help install dev test ui-test pages vercel lint fmt contract contract-test build up down smoke \
	model fetch-models verify-models serve profiles core-cmd kv-budget index audio \
	bench profile monitor bench-target eval backup restore \
	bench-native-linux export-native-linux \
	desktop-models desktop-native desktop-stage desktop-freeze desktop-build desktop-test \
	final-package final-packages

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the app + dev tooling (editable)
	$(PY) -m pip install -e ".[dev]"

dev: ## Run the gateway with reload on the host (SQLite; http://127.0.0.1:8000)
	TUTOR_ROOT=$(CURDIR) $(PY) -m uvicorn orchestrator.main:app --reload --port 8000

test: ## Run tests (portable SQLite always; Postgres parity tests use compose db or skip)
	$(PY) -m pytest

ui-test: ## Run browser-client unit tests without starting the backend
	node --test ui/tests/*.test.js

pages: ## Render the Muta IQ report as a static site in site/ (what .github/workflows/pages.yml deploys)
	$(PY) muta-iq/dashboard/build_static.py --out site

vercel: ## Deploy the Muta IQ report to Vercel as a prebuilt static site (docs/report-hosting.md)
	scripts/deploy_report_vercel.sh

lint: ## Lint (ruff)
	$(PY) -m ruff check .

fmt: ## Format (ruff)
	$(PY) -m ruff format .

contract: ## Regenerate contracts/openapi.yaml from the Pydantic models
	$(PY) -m contracts.openapi

contract-test: ## Property-fuzz a running server against the contract (needs `make dev`)
	schemathesis run http://127.0.0.1:8000/openapi.json --checks all

# --- The 3-container stack ---
build: ## Build the db/backend/frontend images (linux/amd64)
	MUTA_BUILD_GIT_SHA=$$($(PY) scripts/source_identity.py --id) docker compose build

up: ## Start the stack and wait for health (db -> backend -> frontend)
	docker compose up -d --wait

down: ## Stop the stack (conversations survive in the muta-pgdata volume)
	docker compose down

smoke: ## Quick end-to-end probe against a running stack
	@curl -fsS http://localhost:8000/v1/ready && echo && \
	curl -fsS http://localhost:3000/v1/health && echo

# --- Models ---
model: ## Download the small dev GGUF (Qwen3-0.6B Q4_K_M) into models/
	$(PY) -c "from runtime.config import RuntimeConfig; from runtime.models import download_from_hf; download_from_hf(RuntimeConfig())"

fetch-models: ## Download the full pinned roster + write MANIFEST.json. Args: ARGS="--dry-run"
	scripts/fetch_models.sh $(ARGS)

verify-models: ## Acceptance checks for the fetched roster: hashes, budget, licences, load smoke
	scripts/verify_models.sh $(ARGS)

fetch-ttft: ## Download+convert the TTFT preamble model (opt-in; licence unresolved — docs/ttft-preamble.md)
	$(PY) scripts/fetch_ttft_model.py $(ARGS)

# --- Host-side runtime tools ---
serve: ## Launch llama-server on the host against the resolved model
	$(PY) -m runtime.server

profiles: ## Show the serving profile + thread allocation for THIS box
	$(PY) -m runtime.profiles table

core-cmd: ## Print the exact llama-server invocation for a profile. Args: PROFILE=solo-demo
	PROFILE=$(PROFILE) $(PY) -m runtime.profiles print core

kv-budget: ## Regenerate the KV/slot budget table from a GGUF's own metadata
	$(PY) -m runtime.kvmath $(MODEL) --markdown docs/kv-budget.md

index: ## Build the RAG index from a chunked corpus. Args: CORPUS=... OUT=index/
	$(PY) -m orchestrator.retrieval.index build --corpus $(CORPUS) --out $(or $(OUT),index)

audio: ## Run the standalone ASR/TTS websocket service (the gateway also serves /v1/audio)
	TUTOR_ROOT=$(CURDIR) $(PY) -m orchestrator.audio.service

# --- Measurement ---
bench: ## Product-path pass against a running app. Args: ARGS="--pid <n>"
	$(PY) -m bench.profile $(ARGS)

profile: ## Official profiler + product path, both scored. Args: ARGS="--skip-product"
	$(PY) -m bench.autotest $(ARGS)

monitor: ## Live scored-metrics HUD against a running app. Args: ARGS="--pid <n>"
	$(PY) -m bench.monitor $(ARGS)

bench-target: ## Engine bench in a target-box-shaped container (8 GiB, 6C+SMT). Args: ARGS="-- --sweep WINNER"
	scripts/bench_target_box.sh $(ARGS)

export-native-linux: ## One-time verified engine extraction from muta-backend:latest (Linux x86-64)
	./run.sh export-linux

bench-native-linux: ## Bare GCP x86 cloud-proxy bench; exploratory. Args: ARGS="--sweep LINUX-PRODUCT"
	scripts/bench_native_linux.sh $(ARGS)

eval: ## Tutoring-quality eval (the 50% S_acc term) against a running stack. Args: ARGS="--base http://localhost:3000"
	$(PY) -m bench.eval $(ARGS)

# --- Data safety (student conversations live only in the muta-pgdata volume) ---
backup: ## Dump the Postgres db to backups/muta-<timestamp>.dump (compressed, restorable)
	@mkdir -p backups
	@ts=$$(date +%Y%m%d-%H%M%S); \
	 out=backups/muta-$$ts.dump; \
	 docker compose exec -T db pg_dump -U muta -Fc muta > $$out \
	   && echo "wrote $$out ($$(du -h $$out | cut -f1))" \
	   || { echo "backup failed — is the db up? (make up)"; rm -f $$out; exit 1; }

restore: ## Restore from a dump: make restore DUMP=backups/muta-<ts>.dump  (DESTRUCTIVE)
	@test -n "$(DUMP)" || { echo "usage: make restore DUMP=backups/muta-<timestamp>.dump"; exit 2; }
	@test -f "$(DUMP)" || { echo "no such dump: $(DUMP)"; exit 2; }
	@echo "restoring $(DUMP) into the muta db (existing data is replaced)…"
	docker compose exec -T db pg_restore -U muta -d muta --clean --if-exists < "$(DUMP)"

# --- Native desktop packaging (always runs on the target OS/architecture) ---
desktop-models: ## Provision the verified offline tutor, vision, voice and retrieval models
	scripts/prepare_desktop_models.sh

desktop-native: ## Build pinned llama.cpp + FFmpeg for this native runner
	scripts/build_desktop_native.sh desktop/build/native

desktop-stage: ## Stage signed app resources + separate verified model pack. Args: ARGS="..."
	$(PY) scripts/stage_desktop.py stage $(ARGS)

desktop-freeze: ## Build/test the PyInstaller onedir sidecar without Tauri. Args: ARGS="..."
	$(PY) scripts/build_desktop.py --no-tauri $(ARGS)

desktop-build: ## Build the native Tauri package and offline portable kit. Args: ARGS="..."
	$(PY) scripts/build_desktop.py $(ARGS)

desktop-test: ## Verify staging/freezer Python and the Tauri launcher
	$(PY) -m pytest desktop/tests scripts/test_stage_desktop.py scripts/test_desktop_release.py runtime/tests/test_paths.py
	cd desktop/src-tauri && cargo fmt --check && cargo test --locked

final-package final-packages: ## Build four cached offline packages from pushed HEAD. Args: ARGS="--version 0.2.0"
	$(PY) scripts/manual_desktop_release.py $(ARGS)

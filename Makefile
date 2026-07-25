# Muta — developer entrypoints. `make help` lists everything.
# Real targets work today; Phase-1+ targets echo their ROADMAP reference until built.
.DEFAULT_GOAL := help
PY ?= python3
IMAGE ?= muta-dev:latest
# Baked into the image: the container has no .git, and a benchmark number without provenance
# is unusable in the report (ROADMAP 16 Jul). The -dirty suffix is load-bearing: `COPY . .`
# copies the WORKING TREE, so a build from an uncommitted tree would otherwise tag the image
# with a commit that does not describe the code inside it.
GIT_SHA ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)$(shell test -z "$$(git status --porcelain 2>/dev/null)" || echo -dirty)

.PHONY: help install dev test lint fmt contract contract-test build smoke bench profile monitor tui package \
	profiles core-cmd kv-budget engine fetch-models verify-models manifest stage selftest index audio

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the app + dev tooling (editable)
	$(PY) -m pip install -e ".[dev]"

dev: ## Run the assembled app with reload (http://127.0.0.1:8000, docs at /docs)
	$(PY) -m uvicorn orchestrator.main:app --reload --port 8000

test: ## Run the test suite
	$(PY) -m pytest

lint: ## Lint (ruff)
	$(PY) -m ruff check .

fmt: ## Format (ruff)
	$(PY) -m ruff format .

contract: ## Regenerate contracts/openapi.yaml from the Pydantic models
	$(PY) -m contracts.openapi

contract-test: ## Property-fuzz a running server against the contract (needs `make dev`)
	schemathesis run http://127.0.0.1:8000/openapi.json --checks all

build: ## Build the linux/amd64 dev image
	docker buildx build --platform=linux/amd64 -f docker/dev.Dockerfile \
		--build-arg MUTA_GIT_SHA=$(GIT_SHA) -t $(IMAGE) .

model: ## Download the default GGUF (Qwen3-0.6B Q4_K_M) into models/
	$(PY) -c "from runtime.config import RuntimeConfig; from runtime.models import download_from_hf; download_from_hf(RuntimeConfig())"

serve: ## Launch the llama.cpp inference server (resolves model: folder, else HF)
	$(PY) -m runtime.server

chat: ## Interactive multi-turn REPL. Args: make chat ARGS="--conversation <id>"
	$(PY) -m runtime.cli $(ARGS)

# --- Deploy bundle (TDD §10, §11) ---
profiles: ## Show the serving profile + thread allocation for THIS box (TDD §6.2/§6.4)
	$(PY) -m runtime.profiles table

core-cmd: ## Print the exact llama-server invocation for a profile. Args: PROFILE=solo-demo
	PROFILE=$(PROFILE) $(PY) -m runtime.profiles print core

kv-budget: ## Regenerate the KV/slot budget table from a GGUF's own metadata (TDD T5)
	$(PY) -m runtime.kvmath $(MODEL) --markdown docs/kv-budget.md

engine: ## Build inference engine variant A from the pinned tree (TDD T1)
	deploy/build.sh

fetch-models: ## Download models by exact revision + write MANIFEST.json (TDD T2, build machine only)
	scripts/fetch_models.sh $(ARGS)

verify-models: ## Acceptance checks for the fetched bundle: hashes, budget, licences, load smoke (TDD T2)
	scripts/verify_models.sh $(ARGS)

manifest: ## Verify a bundle against its manifest. Args: ROOT=dist
	$(PY) -m bundle.manifest verify --root $(or $(ROOT),dist)

stage: ## USB -> local disk with dual hash verify (TDD §10.3). Args: SRC=/media/usb/tutor
	deploy/stage.sh --src $(SRC) --dst $(or $(DST),/opt/tutor)

selftest: ## Clean-room self test against a staged bundle (TDD T16)
	deploy/selftest.sh --root $(or $(ROOT),/opt/tutor)

index: ## Build the RAG index from a chunked corpus (TDD T11). Args: CORPUS=... OUT=index/
	$(PY) -m orchestrator.retrieval.index build --corpus $(CORPUS) --out $(or $(OUT),index)

audio: ## Run the ASR/TTS websocket service (TDD §6.6)
	$(PY) -m orchestrator.audio.service

# --- Phase-1+ targets (not yet implemented — see ROADMAP.md) ---
smoke: ## [TODO 17 Jul] docker run -> server -> health -> prompt -> profiler JSON
	@echo "not implemented — see ROADMAP.md (Fri 17 Jul, 'make smoke')"

bench: ## Product-path pass against a running app (fast loop). Args: ARGS="--pid <n>"
	$(PY) -m bench.profile $(ARGS)

profile: ## Autonomous: official profiler + product path, both scored. Args: ARGS="--skip-product"
	$(PY) -m bench.autotest $(ARGS)

monitor: ## Live scored-metrics HUD against a running app. Args: ARGS="--pid <n>"
	$(PY) -m bench.monitor $(ARGS)

tui: ## Chat TUI with a live metrics panel (needs a running app: ./run.sh --serve)
	$(PY) -m bench.tui $(ARGS)

package: ## Assemble dist/ in the §10.1 shape and rehearse it in a clean room (TDD T16)
	deploy/package.sh $(ARGS)

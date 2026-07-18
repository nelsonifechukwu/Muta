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

.PHONY: help install dev test lint fmt contract contract-test build smoke bench profile package

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

# --- Phase-1+ targets (not yet implemented — see ROADMAP.md) ---
smoke: ## [TODO 17 Jul] docker run -> server -> health -> prompt -> profiler JSON
	@echo "not implemented — see ROADMAP.md (Fri 17 Jul, 'make smoke')"

bench: ## [TODO 16 Jul] profile.py (end-to-end) + llama-bench (engine ceiling)
	@echo "not implemented — see ROADMAP.md (Thu 16 Jul, bench/profile.py)"

profile: ## [TODO 16 Jul] wire in the official ADTC local profiler
	@echo "not implemented — see ROADMAP.md (Thu 16 Jul, 'make profile')"

package: ## [TODO 9 Aug] extract container -> native portable build (AppImage)
	@echo "not implemented — see docs/native-extraction-plan.md"

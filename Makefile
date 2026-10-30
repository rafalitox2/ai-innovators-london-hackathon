# ============================================================================
# AI Innovators Expedition — London Hackathon Starter Makefile
# Works with GNU Make on macOS and Linux. On Windows use WSL2 (Ubuntu), or run
# the `.venv/bin/python -m ...` commands shown below directly.
# ============================================================================

SHELL := /bin/bash
PORT ?= 8000

# Resolve primary git worktree so secondary `git worktree` checkouts automatically
# share `.venv` and `.env` even before `make worktree-link` or `make setup` runs.
MAIN_WORKTREE := $(shell git worktree list --porcelain 2>/dev/null | awk '/^worktree / {print substr($$0, 10); exit}')
ifeq (,$(wildcard .venv/bin/python))
    ifneq (,$(wildcard $(MAIN_WORKTREE)/.venv/bin/python))
        VENV_DIR := $(MAIN_WORKTREE)/.venv
    else
        VENV_DIR := .venv
    endif
else
    VENV_DIR := .venv
endif
PYTHON := $(VENV_DIR)/bin/python
ADK := $(VENV_DIR)/bin/adk

# .env is read by Make as KEY=value lines: do not quote values, no spaces around '='.
ifneq (,$(wildcard ./.env))
    include .env
    export
else ifneq (,$(wildcard $(MAIN_WORKTREE)/.env))
    include $(MAIN_WORKTREE)/.env
    export
endif

PACK ?= $(SEED_PACK)

.PHONY: help setup check-venv seed dev eval eval-validate test test-adk test-a2a test-mcp benchmark-mcp test-adk-gcp test-a2a-gcp benchmark-mcp-gcp verify worktree worktree-link worktree-list deploy test-remote delete ui-install ui-dev ui-build ui-api

help:
	@echo "AI Innovators Expedition — Starter & Multi-Worktree Commands:"
	@echo "  make setup                    Create Python 3.12 .venv with uv and install dependencies"
	@echo "  make worktree BRANCH=feat/x   Create isolated git worktree (../wt-x) with linked .venv & .env"
	@echo "  make worktree-link            Symlink .venv and .env from primary worktree into current worktree"
	@echo "  make worktree-list            List all active git worktrees and branches"
	@echo "  make verify [PACK=t02]        Run full offline PR gate (pytest + eval-validate + check_packs)"
	@echo "  make seed PACK=t02            Load Seed Pack data into BigQuery & Cloud Storage"
	@echo "  make dev                      Launch local ADK Web UI (http://127.0.0.1:$(PORT))"
	@echo "  make ui-api                   Launch integrated FastAPI + ADK server for /ui (http://127.0.0.1:$(PORT))"
	@echo "  make ui-install               Install npm dependencies in /ui"
	@echo "  make ui-dev                   Launch Vite dev server for Nocturne React UI (http://127.0.0.1:5173)"
	@echo "  make ui-build                 Build production bundle in /ui/dist"
	@echo "  make eval [PACK=t02]          Run the golden evaluation cases (live Gemini calls)"
	@echo "  make eval-validate [PACK=t02] Validate eval files only (no Gemini calls)"
	@echo "  make test                     Run fast offline unit tests (pytest)"
	@echo "  make test-adk                 Run isolated ADK Agent & GCP evaluator suite (offline)"
	@echo "  make test-a2a                 Run isolated A2A Protocol & Tribe handshake suite (offline)"
	@echo "  make test-mcp                 Run isolated FastMCP SDK, OOP services & Gateway suite (offline)"
	@echo "  make benchmark-mcp            Run MCP Latency (p50/p95/p99), Throughput & Concurrency Benchmark"
	@echo "  make test-adk-gcp             Run Live GCP ADK suite (Vertex AI Eval + BigQuery dry-run + Agent Engine)"
	@echo "  make test-a2a-gcp             Run Live GCP A2A suite (Cloud Run OIDC + JSON-RPC 2.0 + Tribe Sync)"
	@echo "  make benchmark-mcp-gcp        Run Live GCP Cloud Run MCP Latency & Throughput Benchmark"
	@echo "  make deploy [PACK=t02]        Deploy/update the agent on Vertex AI Agent Runtime"
	@echo "                                (ARGS=--create-new forces a second, new agent)"
	@echo "  make test-remote [PROMPT=..]  Send a live verification query to the deployed agent"
	@echo "  make delete [RESOURCE=..]     Delete the deployed agent (default: the one saved by make deploy)"

setup:
	@command -v uv >/dev/null 2>&1 || { \
		echo "ERROR: 'uv' is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; }
	uv venv --python 3.12 .venv
	uv pip install --python $(PYTHON) -r pyproject.toml

check-venv:
	@test -x $(PYTHON) || { echo "ERROR: $(PYTHON) not found. Run 'make setup' first."; exit 1; }

seed: check-venv
	@if [ -z "$(PACK)" ]; then \
		echo "ERROR: Set PACK=<id> (e.g. make seed PACK=t08) or set SEED_PACK in .env"; \
		exit 1; \
	fi
	@$(PYTHON) -c 'import runpy, sys; from app.loader import resolve_pack_directory; d = resolve_pack_directory(sys.argv[1]); runpy.run_path(str(d / "load.py"), run_name="__main__")' "$(PACK)"

dev: check-venv
	$(ADK) web . --port $(PORT)

ui-api: check-venv
	$(PYTHON) -m app.ui_server --port $(PORT)

ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

eval: check-venv
	@if [ -n "$(PACK)" ]; then \
		SEED_PACK="$(PACK)" $(PYTHON) -m eval.run_eval --pack "$(PACK)"; \
	else \
		$(PYTHON) -m eval.run_eval; \
	fi

eval-validate: check-venv
	@if [ -n "$(PACK)" ]; then \
		SEED_PACK="$(PACK)" $(PYTHON) -m eval.run_eval --pack "$(PACK)" --validate-only; \
	else \
		$(PYTHON) -m eval.run_eval --validate-only; \
	fi

test: check-venv
	$(PYTHON) -m pytest -q

test-adk: check-venv
	@echo "=== Running Isolated Google ADK Agent & Evaluator Suite ==="
	$(PYTHON) -m pytest tests/adk -v
	$(PYTHON) -m eval.adk_suite_runner --mode offline --pack "$(or $(PACK),t02)"

test-a2a: check-venv
	@echo "=== Running Isolated Official A2A Protocol & Tribe Handshake Suite ==="
	$(PYTHON) -m pytest tests/a2a -v
	$(PYTHON) -m eval.a2a_suite_runner --mode offline

test-mcp: check-venv
	@echo "=== Running Isolated FastMCP SDK, OOP Services & Gateway Suite ==="
	$(PYTHON) -m pytest tests/mcp -v

benchmark-mcp: check-venv
	@echo "=== Running MCP Latency (p50/p95/p99), Throughput & Concurrency Benchmark ==="
	$(PYTHON) -m eval.mcp_benchmark_runner --mode offline $(ARGS)

test-adk-gcp: check-venv
	@echo "=== Running Live GCP ADK Suite (Vertex AI Eval + BigQuery Dry-Run + Agent Engine) ==="
	SEED_PACK="$(or $(PACK),t02)" $(PYTHON) -m eval.adk_suite_runner --mode gcp --pack "$(or $(PACK),t02)" $(ARGS)

test-a2a-gcp: check-venv
	@echo "=== Running Live GCP A2A Suite (Cloud Run OIDC + JSON-RPC 2.0 + Tribe Sync) ==="
	$(PYTHON) -m eval.a2a_suite_runner --mode gcp $(ARGS)

benchmark-mcp-gcp: check-venv
	@echo "=== Running Live GCP Cloud Run MCP Latency & Throughput Benchmark ==="
	$(PYTHON) -m eval.mcp_benchmark_runner --mode gcp $(ARGS)

verify: check-venv
	@echo "=== [1/3] Offline unit test suite (pytest) ==="
	$(PYTHON) -m pytest -q
	@echo "=== [2/3] Golden evaluation schema validation (PACK=$(or $(PACK),t02)) ==="
	SEED_PACK="$(or $(PACK),t02)" $(PYTHON) -m eval.run_eval --pack "$(or $(PACK),t02)" --validate-only
	@echo "=== [3/3] Active Seed Packs contract check ==="
	$(PYTHON) -m seed_packs.check_packs

worktree:
	@if [ -z "$(BRANCH)" ]; then \
		echo "ERROR: Set BRANCH=<type>/<slug> (e.g. make worktree BRANCH=feat/my-feature)"; \
		exit 1; \
	fi
	@SLUG=$$(echo "$(BRANCH)" | sed -E 's#^(feat|fix|ci|docs|chore)/##; s#[^a-zA-Z0-9_-]#-#g'); \
	WT_DIR="$(if $(DIR),$(DIR),../wt-$$SLUG)"; \
	git fetch origin main >/dev/null 2>&1 || true; \
	if git show-ref --verify --quiet "refs/heads/$(BRANCH)"; then \
		git worktree add "$$WT_DIR" "$(BRANCH)"; \
	else \
		BASE_REF=$$(git rev-parse --verify --quiet origin/main >/dev/null && echo "origin/main" || echo "HEAD"); \
		git worktree add "$$WT_DIR" -b "$(BRANCH)" "$$BASE_REF"; \
	fi; \
	if [ -n "$(MAIN_WORKTREE)" ] && [ -d "$(MAIN_WORKTREE)/.venv" ] && [ ! -e "$$WT_DIR/.venv" ]; then \
		ln -s "$(MAIN_WORKTREE)/.venv" "$$WT_DIR/.venv"; \
	fi; \
	if [ -n "$(MAIN_WORKTREE)" ] && [ -f "$(MAIN_WORKTREE)/.env" ] && [ ! -e "$$WT_DIR/.env" ]; then \
		cp "$(MAIN_WORKTREE)/.env" "$$WT_DIR/.env"; \
	fi; \
	echo "Worktree ready at $$WT_DIR (branch: $(BRANCH)). Next: cd $$WT_DIR && make verify"

worktree-link:
	@if [ -z "$(MAIN_WORKTREE)" ]; then \
		echo "ERROR: Not inside a git worktree."; \
		exit 1; \
	fi
	@if [ ! -e ".venv" ] && [ -d "$(MAIN_WORKTREE)/.venv" ]; then \
		ln -s "$(MAIN_WORKTREE)/.venv" .venv; \
		echo "Linked .venv -> $(MAIN_WORKTREE)/.venv"; \
	fi
	@if [ ! -e ".env" ] && [ -f "$(MAIN_WORKTREE)/.env" ]; then \
		cp "$(MAIN_WORKTREE)/.env" .env; \
		echo "Copied .env from $(MAIN_WORKTREE)/.env"; \
	fi

worktree-list:
	@git worktree list

deploy: check-venv
	@if [ -n "$(PACK)" ]; then \
		SEED_PACK="$(PACK)" $(PYTHON) -m deploy.deploy --pack "$(PACK)" $(ARGS); \
	else \
		$(PYTHON) -m deploy.deploy $(ARGS); \
	fi

test-remote: check-venv
	$(PYTHON) -m deploy.test_remote $(if $(PROMPT),--message "$(PROMPT)",)

delete: check-venv
	$(PYTHON) -m deploy.delete $(if $(RESOURCE),--resource-name "$(RESOURCE)",)

cd-deploy:
	bash cd/deploy_cd.sh

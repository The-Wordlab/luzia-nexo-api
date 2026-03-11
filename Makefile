SHELL := /bin/bash

GCP_PROJECT_ID ?= luzia-nexo-api-examples
GCP_REGION ?= europe-west1
VENV_BIN ?= $(CURDIR)/.venv/bin
PYTEST ?= $(VENV_BIN)/pytest

.PHONY: setup-dev check-toolchain check-mermaid test-demo-receiver test-examples test-rag-examples test-contracts test-hosted-examples test-sdk test-all gcp-bootstrap gcp-bootstrap-check deploy-demo-receiver deploy-examples-py deploy-examples-ts deploy-examples deploy-rag-examples deploy-rag-workers deploy-all-examples setup-rag-scheduler setup-rag-worker-scheduler set-rag-mode-worker set-rag-mode-endpoint check-rag-scheduler check-rag-worker-scheduler check-rag-scheduler-legacy-endpoint setup-rag-production setup-rag-production-legacy-endpoint setup-rag-production-workers verify-examples smoke-live-services seed-demo-local seed-demo seed-demo-dry-run docs-build docs-serve

setup-dev:
	./scripts/setup-dev.sh

check-toolchain:
	./scripts/check-toolchain.sh

check-mermaid:
	python3 scripts/check_mermaid.py

test-demo-receiver:
	@if [ ! -x "$(PYTEST)" ]; then echo "ERROR: $(PYTEST) not found. Run 'make setup-dev' first."; exit 1; fi
	cd examples/hosted/demo-receiver && $(PYTEST) -q

test-examples:
	./scripts/test-examples.sh

test-rag-examples:
	./scripts/test-rag-examples.sh

test-contracts:
	@if [ ! -x "$(PYTEST)" ]; then echo "ERROR: $(PYTEST) not found. Run 'make setup-dev' first."; exit 1; fi
	cd tests/contracts && $(PYTEST) -q

test-hosted-examples:
	./scripts/test-hosted-examples.sh

test-sdk:
	cd sdk/javascript && source ~/.zshrc && pnpm install --no-frozen-lockfile && pnpm test

test-all: test-demo-receiver test-examples test-rag-examples test-contracts test-hosted-examples test-sdk

gcp-bootstrap:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/bootstrap-gcp.sh

gcp-bootstrap-check:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/bootstrap-gcp.sh >/dev/null

deploy-demo-receiver:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) SERVICE_NAME=nexo-demo-receiver ./examples/hosted/demo-receiver/deploy/cloudrun/deploy.sh

deploy-examples-py:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) SERVICE_NAME=nexo-examples-py ./examples/hosted/python/deploy/cloudrun/deploy.sh

deploy-examples-ts:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) SERVICE_NAME=nexo-examples-ts ./examples/hosted/typescript/deploy/cloudrun/deploy.sh

deploy-examples: deploy-examples-py deploy-examples-ts

deploy-rag-examples:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/deploy-rag-examples.sh all

deploy-rag-workers:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/deploy-rag-workers.sh all

deploy-all-examples:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/deploy-all-examples.sh all

setup-rag-scheduler:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/setup-rag-scheduler.sh all

setup-rag-worker-scheduler:
	@if [ -z "$$SCHEDULER_RUNNER_SA" ]; then echo "ERROR: SCHEDULER_RUNNER_SA is required"; exit 1; fi
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) SCHEDULER_RUNNER_SA=$$SCHEDULER_RUNNER_SA ./scripts/setup-rag-worker-scheduler.sh all

set-rag-mode-worker:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/set-rag-scheduler-mode.sh worker

set-rag-mode-endpoint:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/set-rag-scheduler-mode.sh endpoint

check-rag-scheduler:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/check-rag-scheduler.sh worker

check-rag-scheduler-legacy-endpoint:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/check-rag-scheduler.sh endpoint

check-rag-worker-scheduler:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/check-rag-scheduler.sh worker

setup-rag-production: deploy-rag-examples deploy-rag-workers setup-rag-worker-scheduler set-rag-mode-worker check-rag-worker-scheduler

setup-rag-production-workers: deploy-rag-examples deploy-rag-workers setup-rag-worker-scheduler check-rag-worker-scheduler

setup-rag-production-legacy-endpoint: deploy-rag-examples setup-rag-scheduler set-rag-mode-endpoint check-rag-scheduler

verify-examples:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/verify-hosted-examples.sh

smoke-live-services:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/smoke-live-services.sh

seed-demo-local: ## Seed demo apps against local Nexo (http://localhost:8000)
	python3 scripts/seed-demo-apps.py --env local

seed-demo: ## Seed demo apps (reads --env flag, default: local)
	python3 scripts/seed-demo-apps.py

seed-demo-dry-run: ## Preview demo seed without making changes
	python3 scripts/seed-demo-apps.py --dry-run

docs-build:
	$(MAKE) check-toolchain
	$(MAKE) check-mermaid
	@if [ ! -x "$(VENV_BIN)/mkdocs" ]; then echo "ERROR: $(VENV_BIN)/mkdocs not found. Run 'make setup-dev' first."; exit 1; fi
	$(VENV_BIN)/mkdocs build --strict

docs-serve:
	@if [ ! -x "$(VENV_BIN)/mkdocs" ]; then echo "ERROR: $(VENV_BIN)/mkdocs not found. Run 'make setup-dev' first."; exit 1; fi
	$(VENV_BIN)/mkdocs serve

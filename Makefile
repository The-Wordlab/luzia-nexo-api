SHELL := /bin/bash

GCP_PROJECT_ID ?= luzia-nexo-api-examples
GCP_REGION ?= europe-west1
VENV_BIN ?= $(CURDIR)/.venv/bin
PYTHON ?= $(VENV_BIN)/python
PYTEST ?= $(VENV_BIN)/pytest

.PHONY: setup-dev pre-commit check-toolchain check-mermaid test-examples test-contracts test-hosted-examples test-sdk test-all gcp-bootstrap gcp-bootstrap-check deploy-examples-py deploy-examples-ts deploy-examples deploy-all-examples verify-examples smoke-live-services seed-demo-local seed-demo seed-demo-dry-run docs-build docs-serve

pre-commit:
	$(VENV_BIN)/pre-commit run --all-files

setup-dev:
	source ~/.zshrc && ./scripts/setup-dev.sh

check-toolchain:
	source ~/.zshrc && ./scripts/check-toolchain.sh

check-mermaid:
	@if [ ! -x "$(PYTHON)" ]; then echo "ERROR: $(PYTHON) not found. Run 'make setup-dev' first."; exit 1; fi
	$(PYTHON) scripts/check_mermaid.py

test-examples:
	source ~/.zshrc && ./scripts/test-examples.sh

test-contracts:
	@if [ ! -x "$(PYTEST)" ]; then echo "ERROR: $(PYTEST) not found. Run 'make setup-dev' first."; exit 1; fi
	cd tests/contracts && $(PYTEST) -q

test-hosted-examples:
	source ~/.zshrc && ./scripts/test-hosted-examples.sh

test-sdk:
	cd sdk/javascript && source ~/.zshrc && pnpm install --no-frozen-lockfile && pnpm test

test-all: test-examples test-contracts test-hosted-examples test-sdk

gcp-bootstrap:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/bootstrap-gcp.sh

gcp-bootstrap-check:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/bootstrap-gcp.sh >/dev/null

deploy-examples-py:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) SERVICE_NAME=nexo-examples-py ./examples/hosted/python/deploy/cloudrun/deploy.sh

deploy-examples-ts:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) SERVICE_NAME=nexo-examples-ts ./examples/hosted/typescript/deploy/cloudrun/deploy.sh

deploy-examples: deploy-examples-py deploy-examples-ts

deploy-all-examples:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/deploy-all-examples.sh all

verify-examples:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/verify-hosted-examples.sh

smoke-live-services:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/smoke-live-services.sh

seed-demo-local: ## Seed demo apps against local Nexo (http://localhost:8000)
	$(PYTHON) scripts/seed-demo-apps.py --env local

seed-demo: ## Seed demo apps (reads --env flag, default: local)
	$(PYTHON) scripts/seed-demo-apps.py

seed-demo-dry-run: ## Preview demo seed without making changes
	$(PYTHON) scripts/seed-demo-apps.py --dry-run

docs-build:
	$(MAKE) check-toolchain
	$(MAKE) check-mermaid
	@if [ ! -x "$(VENV_BIN)/mkdocs" ]; then echo "ERROR: $(VENV_BIN)/mkdocs not found. Run 'make setup-dev' first."; exit 1; fi
	$(VENV_BIN)/mkdocs build --strict

docs-serve:
	@if [ ! -x "$(VENV_BIN)/mkdocs" ]; then echo "ERROR: $(VENV_BIN)/mkdocs not found. Run 'make setup-dev' first."; exit 1; fi
	$(VENV_BIN)/mkdocs serve

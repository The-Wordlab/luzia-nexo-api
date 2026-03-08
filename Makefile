SHELL := /bin/bash

GCP_PROJECT_ID ?= luzia-nexo-api-examples
GCP_REGION ?= europe-west1

.PHONY: check-toolchain check-mermaid test-demo-receiver test-examples test-hosted-examples test-sdk test-all gcp-bootstrap gcp-bootstrap-check deploy-demo-receiver deploy-examples-py deploy-examples-ts deploy-examples verify-examples seed-demo-local seed-demo seed-demo-dry-run docs-build docs-serve

check-toolchain:
	./scripts/check-toolchain.sh

check-mermaid:
	python3 scripts/check_mermaid.py

test-demo-receiver:
	cd examples/hosted/demo-receiver && pytest -q

test-examples:
	./scripts/test-examples.sh

test-hosted-examples:
	./scripts/test-hosted-examples.sh

test-sdk:
	cd sdk/javascript && source ~/.zshrc && pnpm install --no-frozen-lockfile && pnpm test

test-all: test-demo-receiver test-examples test-hosted-examples test-sdk

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

verify-examples:
	GCP_PROJECT_ID=$(GCP_PROJECT_ID) GCP_REGION=$(GCP_REGION) ./scripts/verify-hosted-examples.sh

seed-demo-local: ## Seed demo apps against local Nexo (http://localhost:8000)
	python3 scripts/seed-demo-apps.py --env local

seed-demo: ## Seed demo apps (reads --env flag, default: local)
	python3 scripts/seed-demo-apps.py

seed-demo-dry-run: ## Preview demo seed without making changes
	python3 scripts/seed-demo-apps.py --dry-run

docs-build:
	$(MAKE) check-toolchain
	$(MAKE) check-mermaid
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	. .venv/bin/activate && pip install -r docs/requirements-docs.txt && mkdocs build --strict

docs-serve:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	. .venv/bin/activate && pip install -r docs/requirements-docs.txt && mkdocs serve

SHELL := /bin/bash

PROJECT_ID ?= luzia-nexo-api-examples
PROJECT_NUMBER ?= 367427598362
REGION ?= europe-west1

.PHONY: check-toolchain test-demo-receiver test-examples test-hosted-examples test-sdk test-all gcp-bootstrap gcp-bootstrap-check deploy-demo-receiver deploy-examples-py deploy-examples-ts deploy-examples verify-examples docs-build docs-serve

check-toolchain:
	./scripts/check-toolchain.sh

test-demo-receiver:
	cd demo-receiver && pytest -q

test-examples:
	./scripts/test-examples.sh

test-hosted-examples:
	./scripts/test-hosted-examples.sh

test-sdk:
	cd sdk/javascript && source ~/.zshrc && pnpm install --no-frozen-lockfile && pnpm test

test-all: test-demo-receiver test-examples test-hosted-examples test-sdk

gcp-bootstrap:
	PROJECT_ID=$(PROJECT_ID) PROJECT_NUMBER=$(PROJECT_NUMBER) REGION=$(REGION) ./scripts/bootstrap-gcp.sh

gcp-bootstrap-check:
	PROJECT_ID=$(PROJECT_ID) PROJECT_NUMBER=$(PROJECT_NUMBER) REGION=$(REGION) ./scripts/bootstrap-gcp.sh >/dev/null

deploy-demo-receiver:
	PROJECT_ID=$(PROJECT_ID) REGION=$(REGION) SERVICE_NAME=nexo-demo-receiver ./demo-receiver/deploy/cloudrun/deploy.sh

deploy-examples-py:
	PROJECT_ID=$(PROJECT_ID) REGION=$(REGION) SERVICE_NAME=nexo-examples-py ./examples-hosted/python/deploy/cloudrun/deploy.sh

deploy-examples-ts:
	PROJECT_ID=$(PROJECT_ID) REGION=$(REGION) SERVICE_NAME=nexo-examples-ts ./examples-hosted/typescript/deploy/cloudrun/deploy.sh

deploy-examples: deploy-examples-py deploy-examples-ts

verify-examples:
	PROJECT_ID=$(PROJECT_ID) REGION=$(REGION) ./scripts/verify-hosted-examples.sh

docs-build:
	$(MAKE) check-toolchain
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	. .venv/bin/activate && pip install -r docs/requirements-docs.txt && mkdocs build --strict

docs-serve:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	. .venv/bin/activate && pip install -r docs/requirements-docs.txt && mkdocs serve

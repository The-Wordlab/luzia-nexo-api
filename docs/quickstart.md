# Quickstart

Public docs portal:
- `https://the-wordlab.github.io/luzia-nexo-api/`

Runtime pins:
- Node.js `22` (`.nvmrc`)
- Python `3.12` (`.python-version`)

## GCP bootstrap (required before deploy)

Target project:
- Project ID: `luzia-nexo-api-examples`
- Project number: `367427598362`
- Default region: `europe-west1`

Install required tooling (macOS):

```bash
brew install --cask google-cloud-sdk
brew install terraform
```

Authenticate once (interactive):

```bash
gcloud auth login --update-adc
gcloud auth application-default login
```

Set defaults and required APIs from repo root:

```bash
make gcp-bootstrap
```

For internal vs external project setup details and required IAM roles, see `docs/gcp-projects.md`.

This automates:
- `gcloud` default project -> `luzia-nexo-api-examples`
- ADC quota project -> `luzia-nexo-api-examples`
- default run region -> `europe-west1`
- required APIs enablement
- Artifact Registry repo creation (`nexo-examples`)

## Deploy demo receiver to Cloud Run

Set folder-local deploy defaults once:

```bash
cp demo-receiver/deploy/cloudrun/env.example demo-receiver/deploy/cloudrun/env.local
```

Edit `demo-receiver/deploy/cloudrun/env.local` and set `PROJECT_ID=luzia-nexo-api-examples`.

Then deploy with one command:

```bash
make deploy-demo-receiver
```

Direct script invocation still works:

```bash
PROJECT_ID=luzia-nexo-api-examples REGION=europe-west1 ./demo-receiver/deploy/cloudrun/deploy.sh
```

## Deploy hosted examples (Python + TypeScript)

Create local deploy env files:

```bash
cp examples-hosted/python/deploy/cloudrun/env.example examples-hosted/python/deploy/cloudrun/env.local
cp examples-hosted/typescript/deploy/cloudrun/env.example examples-hosted/typescript/deploy/cloudrun/env.local
```

Set the same `EXAMPLES_SHARED_API_SECRET` value in both files. This is the shared API secret both services require for non-health endpoints.
For operational consistency, use the same value you use as the partner app webhook secret in `luzia-nexo` when running demos.
Get/create API secrets in partner portal: `https://nexo.luzia.com/partners`.
Support contact for onboarding issues: `mmm@luzia.com` (Mark MacMahon).

Deploy both services:

```bash
make deploy-examples
```

Verify deployed services:

```bash
make verify-examples EXAMPLES_SHARED_API_SECRET=your-shared-secret
```

Service endpoints after deploy:
- Python hosted examples: `https://.../health`, `POST https://.../webhook/minimal`
- TypeScript hosted examples: `https://.../health`, `POST https://.../webhook/minimal`
- Both hosted services also provide:
  - `GET /` and `GET /info` as default HTML endpoint catalogs
  - JSON variant via `?format=json` or `Accept: application/json`

Current deployed URLs:
- Demo receiver: `https://nexo-demo-receiver-v3me5awkta-ew.a.run.app`
- Hosted Python examples: `https://nexo-examples-py-v3me5awkta-ew.a.run.app`
- Hosted TypeScript examples: `https://nexo-examples-ts-v3me5awkta-ew.a.run.app`

Repository docs:
- `https://github.com/The-Wordlab/luzia-nexo-api`

## Terraform provisioning

```bash
cd infra/terraform/gcp-demo-receiver
terraform init
terraform apply -var="project_id=luzia-nexo-api-examples" -var="region=europe-west1"
```

## Demo receiver local run

```bash
cd demo-receiver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Minimal examples

```bash
python3 examples/webhook/minimal/python/server.py
node examples/webhook/minimal/typescript/webhook-server.mjs
```

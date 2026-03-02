# Quickstart

Public docs portal:
- [the-wordlab.github.io/luzia-nexo-api](https://the-wordlab.github.io/luzia-nexo-api/)

Runtime pins:
- Node.js `22` (`.nvmrc`)
- Python `3.12` (`.python-version`)

## Option A - Use hosted services immediately

Luzia-hosted endpoints:
- Demo receiver: [nexo-demo-receiver](https://nexo-demo-receiver-v3me5awkta-ew.a.run.app)
- Hosted Python examples: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app)
- Hosted TypeScript examples: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app)

Get your API secret from the partner portal:
- [nexo.luzia.com/partners](https://nexo.luzia.com/partners)

Verify availability:

```bash
curl -s https://nexo-examples-py-v3me5awkta-ew.a.run.app/health
curl -s https://nexo-examples-ts-v3me5awkta-ew.a.run.app/health
```

## Option B - Deploy your own copy on GCP

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
PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap
```

This automates:
- `gcloud` default project -> `<your-project-id>`
- ADC quota project -> `<your-project-id>`
- default run region -> `<your-region>`
- required APIs enablement
- Artifact Registry repo creation (`nexo-examples`)

## Deploy demo receiver to Cloud Run

Set folder-local deploy defaults once:

```bash
cp demo-receiver/deploy/cloudrun/env.example demo-receiver/deploy/cloudrun/env.local
```

Edit `demo-receiver/deploy/cloudrun/env.local` and set `PROJECT_ID=luzia-nexo-api-examples`.
Edit `demo-receiver/deploy/cloudrun/env.local` and set:
- `PROJECT_ID=<your-project-id>`
- `REGION=<your-region>`

Then deploy with one command:

```bash
make deploy-demo-receiver
```

Direct script invocation still works:

```bash
PROJECT_ID=<your-project-id> REGION=<your-region> ./demo-receiver/deploy/cloudrun/deploy.sh
```

## Deploy hosted examples (Python + TypeScript)

Create local deploy env files:

```bash
cp examples-hosted/python/deploy/cloudrun/env.example examples-hosted/python/deploy/cloudrun/env.local
cp examples-hosted/typescript/deploy/cloudrun/env.example examples-hosted/typescript/deploy/cloudrun/env.local
```

Set the same `EXAMPLES_SHARED_API_SECRET` value in both files. This is the shared API secret both services require for non-health endpoints.
Get/create API secrets in partner portal: [nexo.luzia.com/partners](https://nexo.luzia.com/partners).
Support contact for onboarding issues: [mmm@luzia.com](mailto:mmm@luzia.com) (Mark MacMahon).

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
- Demo receiver: [nexo-demo-receiver](https://nexo-demo-receiver-v3me5awkta-ew.a.run.app)
- Hosted Python examples: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app)
- Hosted TypeScript examples: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app)

Repository docs:
- [github.com/The-Wordlab/luzia-nexo-api](https://github.com/The-Wordlab/luzia-nexo-api)

## Terraform provisioning

```bash
cd infra/terraform/gcp-demo-receiver
terraform init
terraform apply -var="project_id=<your-project-id>" -var="region=<your-region>"
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

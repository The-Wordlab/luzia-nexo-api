# Hosting (Optional)

You can host your webhook anywhere.

If you want a fast starting point, clone this repository, run the examples, and then extend them for your own integration.

## Required for first live integration

For a real webhook integration with Nexo, you only need:

1. A deployed webhook URL
2. `WEBHOOK_SECRET` shared between your app and Nexo

Everything else on this page is capability expansion for production scale.

## Quick path: clone and run examples

```bash
git clone git@github.com:The-Wordlab/luzia-nexo-api.git
cd luzia-nexo-api
make setup-dev
make test-examples
```

The `examples/` folder contains webhook and Partner API examples you can adapt directly.

Useful shortcuts:

```bash
make deploy-rag-examples
make setup-rag-production
make check-rag-worker-scheduler
```

## Docker (recommended example)

These containers can run in any environment that supports Docker (local machine, VM, Kubernetes, Cloud Run, ECS, etc.). GCP below is only one optional deployment example.

### Python example service

```bash
docker build -t nexo-examples-py ./examples/hosted/python
docker run --rm -p 8080:8080 nexo-examples-py
```

### TypeScript example service

```bash
docker build -t nexo-examples-ts ./examples/hosted/typescript
docker run --rm -p 8080:8080 nexo-examples-ts
```

Optional hardening for hosted examples only (not required for Nexo webhook integration):
```bash
docker run --rm -p 8080:8080 -e EXAMPLES_SHARED_API_SECRET=dev-secret nexo-examples-py
docker run --rm -p 8080:8080 -e EXAMPLES_SHARED_API_SECRET=dev-secret nexo-examples-ts
```

## GCP Cloud Run (unified Cloud Build approach)

All GCP deployments use Cloud Build. There is no Terraform in this repository.

For a minimal, decision-based path (single service vs RAG-only vs full stack),
start with [GCP Deploy Playbook](gcp-deploy-playbook.md), then return here for
full secret/IAM detail.

### Prerequisites

1. **Authenticate**: `gcloud auth login && gcloud auth application-default login`
2. **Set project**: `gcloud config set project <your-project-id>`

### Private server access notes (recommended)

If your team maintains SSH-based operational access, keep those notes in a local-only file:

```bash
mkdir -p docs/private
cp templates/ssh-access.local.template.md docs/private/ssh-access.local.md
```

`docs/private/*.local.md` is git-ignored so sensitive host details stay local.

### Bootstrap a new GCP project

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make gcp-bootstrap
```

The bootstrap script dynamically resolves the project number via `gcloud projects describe`
so you never need to hardcode it. It enables Cloud Run, Cloud Build, Artifact Registry,
Firestore, IAM, and Secret Manager APIs.

### Create required secrets

Cloud Run services read secrets from Secret Manager. Create them before deploying:

| Secret | Used by | Source |
|---|---|---|
| `WEBHOOK_SECRET` | Standard webhook services | Shared HMAC signing secret with Nexo (recommended value: `nexo-example-secret`) |
| `OPENCLAW_WEBHOOK_SECRET` | openclaw-bridge | Dedicated OpenClaw webhook signing secret (recommended value: `nexo-openclaw-secret`) |
| `OPENCLAW_GATEWAY_TOKEN` | openclaw-bridge | Token for your OpenClaw gateway |
| `OPENCLAW_ORIGIN_HEADER_VALUE` | openclaw-bridge | Shared origin key header value for reverse-proxy allowlisting |

```bash
# Create each secret
echo -n "your-value" | gcloud secrets create SECRET_NAME --data-file=-

# Grant Cloud Run access
PROJECT_NUM=$(gcloud projects describe $GCP_PROJECT_ID --format='value(projectNumber)')
for SECRET in WEBHOOK_SECRET OPENCLAW_WEBHOOK_SECRET OPENCLAW_GATEWAY_TOKEN OPENCLAW_ORIGIN_HEADER_VALUE; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${PROJECT_NUM}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" --quiet
done
```

To update a secret value later:
```bash
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=-
```

### Deploy hosted example services

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make deploy-examples
```

### Deploy all server examples (recommended)

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
OPENCLAW_BASE_URL=https://your-openclaw-gateway \
./scripts/deploy-all-examples.sh all
```

This deploys hosted reference services, core webhook examples, flagship orchestration webhooks, and OpenClaw bridge.

### Full live smoke test (all deployed services)

After deployment, run one command to verify discovery + webhook behavior across all Cloud Run examples:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make smoke-live-services
```

Notes:
- Reads `WEBHOOK_SECRET` from Secret Manager.
- Validates signed webhook flows (including OpenClaw bridge).

### End-to-end secret alignment with Nexo (required)

For production, the secret used by Nexo for the OpenClaw app must match the
secret used by `nexo-openclaw-bridge` (`OPENCLAW_WEBHOOK_SECRET`).

Canonical values used in this repository:
- Standard demo webhooks: `nexo-example-secret`
- OpenClaw webhook: `nexo-openclaw-secret`

Apply the same values to Nexo app config via demo seeding:

```bash
export NEXO_API_URL=https://nexo.luzia.com
export NEXO_ADMIN_EMAIL=<admin-email>
export NEXO_ADMIN_PASSWORD=<admin-password>
export DEMO_EXAMPLES_WEBHOOK_SECRET=nexo-example-secret
export DEMO_OPENCLAW_WEBHOOK_SECRET=nexo-openclaw-secret
export DEMO_OPENCLAW_ENABLED=true
python3 scripts/seed-demo-apps.py --env production
```

Then re-run:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make smoke-live-services
```

### OpenClaw connectivity smoke test (recommended before bridge deploy)

Run this from a trusted workstation to verify auth + payload shape:

```bash
BASE='https://<your-openclaw-gateway>/v1/responses'
KEY='<your-openclaw-origin-key>'
TOK='<your-openclaw-gateway-token>'

curl -sS -X POST "$BASE" \
  -H 'Content-Type: application/json' \
  -H "X-Nexo-Bridge-Key: $KEY" \
  -H "Authorization: Bearer $TOK" \
  -H 'x-openclaw-agent-id: main' \
  -H 'x-openclaw-session-key: nexo:test' \
  --data '{"model":"openclaw:main","input":"ping","stream":false}'
```

Expected: `200` with a response payload.
If auth is wrong, expect `401`.
If auth is correct but input shape is wrong, expect `400` (for example array-style `input`).

### OpenClaw hardening and obfuscation model

The bridge-to-OpenClaw path is intentionally protected by layered controls:

1. `X-Nexo-Bridge-Key` header allowlist at reverse proxy (Caddy)
2. `Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>` at OpenClaw gateway
3. Optional bridge ingress key (`BRIDGE_ACCESS_KEY`) at the Cloud Run bridge endpoint

Public docs never include raw secret values. We only document:
- secret names (`OPENCLAW_GATEWAY_TOKEN`, `OPENCLAW_ORIGIN_HEADER_VALUE`)
- where they are used
- how to validate behavior via expected status codes (`401/403/200`)

### Example deployment inventory

Regenerate this table when needed:

```bash
gcloud run services list --region=europe-west1 --format='table(metadata.name,status.url,status.conditions[0].status)'
```

| Service | Region | URL | Health |
|---|---|---|---|
| nexo-examples-py | europe-west1 | `https://nexo-examples-py-v3me5awkta-ew.a.run.app` | - |
| nexo-examples-ts | europe-west1 | `https://nexo-examples-ts-v3me5awkta-ew.a.run.app` | - |
| nexo-webhook-minimal-py | europe-west1 | `https://nexo-webhook-minimal-py-v3me5awkta-ew.a.run.app` | `/webhook` |
| nexo-webhook-structured-py | europe-west1 | `https://nexo-webhook-structured-py-v3me5awkta-ew.a.run.app` | `/` |
| nexo-webhook-advanced-py | europe-west1 | `https://nexo-webhook-advanced-py-v3me5awkta-ew.a.run.app` | `/` |
| nexo-webhook-minimal-ts | europe-west1 | `https://nexo-webhook-minimal-ts-v3me5awkta-ew.a.run.app` | `/` |
| nexo-openclaw-bridge | europe-west1 | `https://nexo-openclaw-bridge-v3me5awkta-ew.a.run.app` | `/` |
| nexo-food-ordering | europe-west1 | `https://nexo-food-ordering-v3me5awkta-ew.a.run.app` | `/` |

### Secrets inventory (example)

| Secret Manager key | Description |
|---|---|
| `WEBHOOK_SECRET` | HMAC-SHA256 signing secret for standard webhook demos (`nexo-example-secret`) |
| `OPENCLAW_WEBHOOK_SECRET` | HMAC-SHA256 signing secret for openclaw-bridge (`nexo-openclaw-secret`) |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw gateway bearer token for openclaw-bridge |
| `EXAMPLES_SHARED_API_SECRET` | Optional auth secret for hosted python/typescript examples (not required by default) |

This deploys sample services only. Your production hosting model is your choice.

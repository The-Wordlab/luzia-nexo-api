# Hosting (Optional)

You can host your webhook anywhere.

If you want a fast starting point, clone this repository, run the examples, and then extend them for your own integration.

## Quick path: clone and run examples

```bash
git clone git@github.com:The-Wordlab/luzia-nexo-api.git
cd luzia-nexo-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip pytest
make test-examples
```

The `examples/` folder contains webhook and Partner API examples you can adapt directly.

## Docker (recommended example)

These containers can run in any environment that supports Docker (local machine, VM, Kubernetes, Cloud Run, ECS, etc.). GCP below is only one optional deployment example.

### Python example service

```bash
docker build -t nexo-examples-py ./examples/hosted/python
docker run --rm -p 8080:8080 \
  -e EXAMPLES_SHARED_API_SECRET=dev-secret \
  nexo-examples-py
```

### TypeScript example service

```bash
docker build -t nexo-examples-ts ./examples/hosted/typescript
docker run --rm -p 8080:8080 \
  -e EXAMPLES_SHARED_API_SECRET=dev-secret \
  nexo-examples-ts
```

## GCP Cloud Run (unified Cloud Build approach)

All GCP deployments use Cloud Build. There is no Terraform in this repository.

### Prerequisites

1. **Authenticate**: `gcloud auth login && gcloud auth application-default login`
2. **Set project**: `gcloud config set project luzia-nexo-api-examples` (or your project)

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
| `WEBHOOK_SECRET` | All webhook services | Shared HMAC signing secret with Nexo |
| `OPENAI_API_KEY` | All RAG services | [platform.openai.com](https://platform.openai.com/api-keys) |
| `FOOTBALL_DATA_API_KEY` | sports-rag, football-live | [football-data.org](https://www.football-data.org/client/register) (free tier: 10 req/min) |
| `OPENCLAW_GATEWAY_TOKEN` | openclaw-bridge | Token for your OpenClaw gateway |
| `OPENCLAW_ORIGIN_HEADER_VALUE` | openclaw-bridge | Shared origin key header value for reverse-proxy allowlisting |
| `EXAMPLES_SHARED_API_SECRET` | hosted python/typescript services | Shared auth secret used by hosted reference endpoints |

```bash
# Create each secret
echo -n "your-value" | gcloud secrets create SECRET_NAME --data-file=-

# Grant Cloud Run access
PROJECT_NUM=$(gcloud projects describe $GCP_PROJECT_ID --format='value(projectNumber)')
for SECRET in WEBHOOK_SECRET OPENAI_API_KEY FOOTBALL_DATA_API_KEY OPENCLAW_GATEWAY_TOKEN OPENCLAW_ORIGIN_HEADER_VALUE EXAMPLES_SHARED_API_SECRET; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${PROJECT_NUM}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" --quiet
done
```

To update a secret value later:
```bash
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=-
```

### Deploy the demo receiver

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make deploy-demo-receiver
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

This deploys hosted services, core webhook examples, OpenClaw bridge, and all RAG services.

For the current Nexo server exposure via Caddy, use:

```bash
OPENCLAW_BASE_URL=https://nexo-1.luzia.com/openclaw
```

### OpenClaw connectivity smoke test (recommended before bridge deploy)

Run this from a trusted workstation to verify auth + payload shape:

```bash
BASE='https://nexo-1.luzia.com/openclaw/v1/responses'
KEY=$(ssh root@46.225.88.64 "grep '^NEXO_BRIDGE_ORIGIN_KEY=' /root/openclaw/.env | cut -d= -f2-")
TOK=$(ssh root@46.225.88.64 "grep '^OPENCLAW_GATEWAY_TOKEN=' /root/openclaw/.env | cut -d= -f2-")

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

### Deploy RAG partner examples

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> ./scripts/deploy-rag-examples.sh all
```

Individual targets: `news`, `sports`, `travel`, `football`.

Each example service has a `cloudbuild.yaml` that handles the full build-push-deploy pipeline on Cloud Run.

### Current deployment (luzia-nexo-api-examples project)

Regenerate this table when needed:

```bash
gcloud run services list --region=europe-west1 --format='table(metadata.name,status.url,status.conditions[0].status)'
```

| Service | Region | URL | Health |
|---|---|---|---|
| nexo-demo-receiver | europe-west1 | `https://nexo-demo-receiver-v3me5awkta-ew.a.run.app` | - |
| nexo-examples-py | europe-west1 | `https://nexo-examples-py-v3me5awkta-ew.a.run.app` | - |
| nexo-examples-ts | europe-west1 | `https://nexo-examples-ts-v3me5awkta-ew.a.run.app` | - |
| nexo-webhook-minimal-py | europe-west1 | `https://nexo-webhook-minimal-py-v3me5awkta-ew.a.run.app` | `/webhook` |
| nexo-webhook-structured-py | europe-west1 | `https://nexo-webhook-structured-py-v3me5awkta-ew.a.run.app` | `/` |
| nexo-webhook-advanced-py | europe-west1 | `https://nexo-webhook-advanced-py-v3me5awkta-ew.a.run.app` | `/` |
| nexo-webhook-minimal-ts | europe-west1 | `https://nexo-webhook-minimal-ts-v3me5awkta-ew.a.run.app` | `/` |
| nexo-openclaw-bridge | europe-west1 | `https://nexo-openclaw-bridge-v3me5awkta-ew.a.run.app` | `/` |
| nexo-news-rag | europe-west1 | `https://nexo-news-rag-v3me5awkta-ew.a.run.app` | `/health` |
| nexo-sports-rag | europe-west1 | `https://nexo-sports-rag-v3me5awkta-ew.a.run.app` | `/health` |
| nexo-travel-rag | europe-west1 | `https://nexo-travel-rag-v3me5awkta-ew.a.run.app` | `/health` |
| nexo-football-live | europe-west1 | `https://nexo-football-live-v3me5awkta-ew.a.run.app` | `/health` |

### Secrets inventory (luzia-nexo-api-examples project)

| Secret Manager key | Description |
|---|---|
| `WEBHOOK_SECRET` | HMAC-SHA256 signing secret shared with Nexo |
| `OPENAI_API_KEY` | OpenAI API key for LLM and embedding calls |
| `FOOTBALL_DATA_API_KEY` | football-data.org API key for live match/standings data |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw gateway bearer token for openclaw-bridge |
| `EXAMPLES_SHARED_API_SECRET` | Shared auth secret for hosted python/typescript examples |

This deploys sample services only. Your production hosting model is your choice.

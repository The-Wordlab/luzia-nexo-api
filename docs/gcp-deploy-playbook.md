# GCP Deploy Playbook

This page is the fastest path to deploy and test examples on GCP.

Use this when you want clear, minimal commands for one target at a time.

## Prerequisites

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project <your-project-id>
```

Bootstrap APIs and baseline infra once:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make gcp-bootstrap
```

## Choose your deployment scope

### A) Deploy one webhook example only

Use this when you want to test a single flow end-to-end without deploying everything.

1. Create required secret:

```bash
echo -n "nexo-example-secret" | gcloud secrets create WEBHOOK_SECRET --data-file=-
```

2. Deploy one service (example: `food-ordering`):

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/deploy-all-examples.sh food-ordering
```

Available single targets:
- `minimal-py`
- `structured-py`
- `advanced-py`
- `minimal-ts`
- `food-ordering`
- `travel-planning`
- `demo-receiver`
- `hosted-py`
- `hosted-ts`
- `openclaw-bridge` (requires OpenClaw secrets)

3. Verify service health:

```bash
gcloud run services describe nexo-food-ordering \
  --region <your-region> \
  --format='value(status.url)'
```

Then call `POST /` on that URL with a webhook payload.

### B) Deploy only RAG services

Use this when you want retrieval examples without the full showcase set.

1. Create required secrets:
- `WEBHOOK_SECRET`
- `NEXO_PGVECTOR_DSN`
- `FOOTBALL_DATA_API_KEY` (for sports/football)

2. Deploy RAG APIs:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/deploy-rag-examples.sh all
```

3. Deploy worker jobs for ingest:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/deploy-rag-workers.sh all
```

4. Configure scheduler (worker mode):

```bash
SCHEDULER_RUNNER_SA=<service-account-email> \
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/setup-rag-worker-scheduler.sh all

GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/set-rag-scheduler-mode.sh worker
```

5. Verify scheduler/worker setup:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/check-rag-scheduler.sh worker
```

6. Verify worker jobs are aligned with the live RAG services:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
./scripts/check-rag-worker-sync.sh
```

### C) Deploy full server-side showcase

Use this when you want the same broad capability surface shown in the public docs.

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> \
OPENCLAW_BASE_URL=https://<your-openclaw-gateway>/openclaw \
./scripts/deploy-all-examples.sh all
```

## Test after deployment

Run one command to verify service discovery + signed webhook paths:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make smoke-live-services
```

Notes:
- Set `RUN_INGEST=false` to skip ingest triggers in smoke.
- OpenClaw checks run only when OpenClaw env/secrets are configured.

## Enforce production secret parity with Nexo

Cloud Run being healthy is not enough. Nexo app secrets must match deployed webhook secrets.

Use these canonical values:
- `DEMO_EXAMPLES_WEBHOOK_SECRET=nexo-example-secret`
- `DEMO_OPENCLAW_WEBHOOK_SECRET=nexo-openclaw-secret`

Important:
- The dedicated OpenClaw secret is only for the OpenClaw app/bridge path.
- All other examples continue using the standard shared demo secret.

Apply them to Nexo:

```bash
export NEXO_API_URL=https://nexo.luzia.com
export NEXO_ADMIN_EMAIL=<admin-email>
export NEXO_ADMIN_PASSWORD=<admin-password>
export DEMO_EXAMPLES_WEBHOOK_SECRET=nexo-example-secret
export DEMO_OPENCLAW_WEBHOOK_SECRET=nexo-openclaw-secret
export DEMO_OPENCLAW_ENABLED=true
python3 scripts/seed-demo-apps.py --env production
```

Then verify with:

```bash
GCP_PROJECT_ID=<your-project-id> GCP_REGION=<your-region> make smoke-live-services
```

## RAG model/runtime defaults

Production intent for RAG examples:
- LLM: Vertex Gemini via ADC
- Embeddings: Vertex embeddings via ADC
- Vector store: `pgvector` on Cloud SQL

Chroma and OpenAI are not part of the supported deployed path.

## Minimal secret matrix by scope

| Scope | Required secrets |
|---|---|
| Single non-RAG webhook | `WEBHOOK_SECRET` |
| RAG only | `WEBHOOK_SECRET`, `NEXO_PGVECTOR_DSN`, `FOOTBALL_DATA_API_KEY` (sports/football only) |
| Full stack without OpenClaw | RAG secrets + `WEBHOOK_SECRET` |
| Full stack with OpenClaw | full stack + `OPENCLAW_WEBHOOK_SECRET`, `OPENCLAW_GATEWAY_TOKEN`, `OPENCLAW_ORIGIN_HEADER_VALUE` |

For full secret creation and IAM binding commands, see [Hosting](hosting.md).

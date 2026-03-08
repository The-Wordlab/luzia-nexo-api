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
| `WEBHOOK_SECRET` | All services | Shared HMAC signing secret with Nexo |
| `OPENAI_API_KEY` | All RAG services | [platform.openai.com](https://platform.openai.com/api-keys) |
| `FOOTBALL_DATA_API_KEY` | sports-rag | [football-data.org](https://www.football-data.org/client/register) (free tier: 10 req/min) |

```bash
# Create each secret
echo -n "your-value" | gcloud secrets create SECRET_NAME --data-file=-

# Grant Cloud Run access
PROJECT_NUM=$(gcloud projects describe $GCP_PROJECT_ID --format='value(projectNumber)')
for SECRET in WEBHOOK_SECRET OPENAI_API_KEY FOOTBALL_DATA_API_KEY; do
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

### Deploy RAG partner examples

```bash
GCP_PROJECT_ID=<your-project-id> ./scripts/deploy-rag-examples.sh all
```

Individual targets: `news`, `sports`, `travel`.

Each example service has a `cloudbuild.yaml` that handles the full build-push-deploy pipeline on Cloud Run.

### Current deployment (luzia-nexo-api-examples project)

| Service | Region | URL |
|---|---|---|
| nexo-demo-receiver | europe-west1 | `https://nexo-demo-receiver-367427598362.europe-west1.run.app` |
| nexo-examples-py | europe-west1 | `https://nexo-examples-py-367427598362.europe-west1.run.app` |
| nexo-examples-ts | europe-west1 | `https://nexo-examples-ts-367427598362.europe-west1.run.app` |
| nexo-news-rag | europe-west1 | `https://nexo-news-rag-367427598362.europe-west1.run.app` |
| nexo-sports-rag | europe-west1 | `https://nexo-sports-rag-367427598362.europe-west1.run.app` |
| nexo-travel-rag | europe-west1 | `https://nexo-travel-rag-367427598362.europe-west1.run.app` |

### Secrets inventory (luzia-nexo-api-examples project)

| Secret Manager key | Description |
|---|---|
| `WEBHOOK_SECRET` | HMAC-SHA256 signing secret shared with Nexo |
| `OPENAI_API_KEY` | OpenAI API key for LLM and embedding calls |
| `FOOTBALL_DATA_API_KEY` | football-data.org API key for live match/standings data |

This deploys sample services only. Your production hosting model is your choice.

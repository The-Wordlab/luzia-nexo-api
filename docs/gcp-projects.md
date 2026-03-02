# GCP Project Setup Guide

This repo supports two deployment modes.

## 1. Internal Luzia project (default)

- Project ID: `luzia-nexo-api-examples`
- Project number: `367427598362`
- Region: `europe-west1`

One-time auth:

```bash
gcloud auth login --update-adc
gcloud auth application-default login
```

Bootstrap from repo root:

```bash
make gcp-bootstrap
```

This configures default `gcloud` project/region, ADC quota project, required APIs, and Artifact Registry repo.

## 2. External partner project (own account)

Use the same flow with override vars:

```bash
PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap
```

Then deploy using the same `make deploy-*` targets.

## Required IAM roles

For users running bootstrap/deploy:

- `roles/run.admin`
- `roles/cloudbuild.builds.editor`
- `roles/artifactregistry.writer`
- `roles/iam.serviceAccountUser`
- `roles/serviceusage.serviceUsageAdmin` (or equivalent to enable APIs)

## Required APIs

Bootstrap enables:

- `run.googleapis.com`
- `cloudbuild.googleapis.com`
- `artifactregistry.googleapis.com`
- `firestore.googleapis.com`
- `iamcredentials.googleapis.com`
- `secretmanager.googleapis.com`
- `serviceusage.googleapis.com`

## Internal live services

- Demo receiver: `https://nexo-demo-receiver-v3me5awkta-ew.a.run.app`
- Hosted Python examples: `https://nexo-examples-py-v3me5awkta-ew.a.run.app`
- Hosted TypeScript examples: `https://nexo-examples-ts-v3me5awkta-ew.a.run.app`

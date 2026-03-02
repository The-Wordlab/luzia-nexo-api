# Terraform - GCP Demo Receiver

Minimal Terraform stack for isolated demo receiver infrastructure.

Resources:

- Cloud Run service
- Service account
- IAM bindings (runtime + optional public invoker)
- Firestore database (native mode) for future persistent store

## Usage

From repo root, bootstrap GCP first:

```bash
make gcp-bootstrap
```

Then provision infra:

```bash
cd infra/terraform/gcp-demo-receiver
terraform init
terraform plan -var="project_id=<project>" -var="region=europe-west1"
terraform apply -var="project_id=<project>" -var="region=europe-west1"
```

This stack is intentionally minimal and separate from production infra.

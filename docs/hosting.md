# Hosting (Optional)

This page is optional. Partners can host their webhook anywhere.

## Docker (recommended example)

### Python example service

```bash
docker build -t nexo-examples-py ./examples-hosted/python
docker run --rm -p 8080:8080 \
  -e EXAMPLES_SHARED_API_SECRET=dev-secret \
  nexo-examples-py
```

### TypeScript example service

```bash
docker build -t nexo-examples-ts ./examples-hosted/typescript
docker run --rm -p 8080:8080 \
  -e EXAMPLES_SHARED_API_SECRET=dev-secret \
  nexo-examples-ts
```

## GCP Cloud Run example (not required)

```bash
PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap
make deploy-examples
```

This deploys sample services only. Your production hosting model is your choice.

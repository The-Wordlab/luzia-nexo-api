# Quickstart

## Hosted path (fastest)

1. Get your app secret at [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
2. Call a hosted endpoint:

```bash
curl -X POST "https://nexo-examples-py-v3me5awkta-ew.a.run.app/webhook/minimal" \
  -H "Content-Type: application/json" \
  -H "X-App-Secret: <your-shared-secret>" \
  -d '{"message":{"content":"hello"}}'
```

## Self-host path (your own GCP project)

```bash
brew install --cask google-cloud-sdk
brew install terraform

gcloud auth login --update-adc
gcloud auth application-default login

PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap

cp examples-hosted/python/deploy/cloudrun/env.example examples-hosted/python/deploy/cloudrun/env.local
cp examples-hosted/typescript/deploy/cloudrun/env.example examples-hosted/typescript/deploy/cloudrun/env.local
# set EXAMPLES_SHARED_API_SECRET in both files

make deploy-examples
make verify-examples EXAMPLES_SHARED_API_SECRET=<your-shared-secret>
```

## Next

- [Examples](examples.md)
- [Partner API Reference](partner-api-reference.md)

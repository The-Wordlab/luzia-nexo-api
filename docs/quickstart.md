# Quickstart

## Hosted path (fastest)

1. Get your app secret at [nexo.luzia.com/partners](https://nexo.luzia.com/partners).
2. Use one hosted endpoint:
   - Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app)
   - TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app)
3. Test with curl:

```bash
curl -X POST "https://nexo-examples-py-v3me5awkta-ew.a.run.app/webhook/minimal" \
  -H "Content-Type: application/json" \
  -H "X-App-Secret: <your-shared-secret>" \
  -d '{"message":{"content":"hello"}}'
```

## Self-host path (your own GCP project)

1. Install tools:

```bash
brew install --cask google-cloud-sdk
brew install terraform
```

2. Authenticate:

```bash
gcloud auth login --update-adc
gcloud auth application-default login
```

3. Bootstrap project:

```bash
PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap
```

4. Configure secrets:

```bash
cp examples-hosted/python/deploy/cloudrun/env.example examples-hosted/python/deploy/cloudrun/env.local
cp examples-hosted/typescript/deploy/cloudrun/env.example examples-hosted/typescript/deploy/cloudrun/env.local
```

Set `EXAMPLES_SHARED_API_SECRET` in both files.

5. Deploy:

```bash
make deploy-examples
```

6. Verify:

```bash
make verify-examples EXAMPLES_SHARED_API_SECRET=<your-shared-secret>
```

## Next

- Example source code: [Examples](examples.md)
- API endpoint details: [Partner API Reference](partner-api-reference.md)
- GitHub repository: [github.com/The-Wordlab/luzia-nexo-api](https://github.com/The-Wordlab/luzia-nexo-api)

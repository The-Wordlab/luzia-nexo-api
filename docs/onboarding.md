# Partner Onboarding (5 minutes)

This guide is for engineers who want to use hosted examples immediately or deploy their own copy on Google Cloud.

## Option A - Use hosted examples now

1. Open endpoint catalog:
   - Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/)
   - TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/)
2. Get your API secret from partner portal:
   - [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
3. Call protected example endpoint:

```bash
curl -X POST "https://nexo-examples-py-v3me5awkta-ew.a.run.app/webhook/minimal" \
  -H "Content-Type: application/json" \
  -H "X-App-Secret: <your-shared-secret>" \
  -d '{"message":{"content":"hello"}}'
```

Need help: [mmm@luzia.com](mailto:mmm@luzia.com) (Mark MacMahon)

## Option B - Deploy your own copy on GCP

1. Authenticate and bootstrap:

```bash
gcloud auth login --update-adc
gcloud auth application-default login
make gcp-bootstrap
```

Deploy to your own project by passing project values explicitly:

```bash
PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap
```

2. Configure local deploy env files:

```bash
cp examples-hosted/python/deploy/cloudrun/env.example examples-hosted/python/deploy/cloudrun/env.local
cp examples-hosted/typescript/deploy/cloudrun/env.example examples-hosted/typescript/deploy/cloudrun/env.local
```

3. Set `EXAMPLES_SHARED_API_SECRET` in both files.

4. Deploy and verify:

```bash
make deploy-examples
make verify-examples EXAMPLES_SHARED_API_SECRET=<your-shared-secret>
```

## Reference

- Full setup: [Quickstart](quickstart.md)
- API and contract details: [Partner API Reference](partner-api-reference.md)
- GitHub: [github.com/The-Wordlab/luzia-nexo-api](https://github.com/The-Wordlab/luzia-nexo-api)

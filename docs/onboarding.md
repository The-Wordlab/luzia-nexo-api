# Partner Onboarding (5 minutes)

Goal: send one request to a hosted example and confirm your integration path.

## 1) Pick a hosted example

- Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/)
- TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/)

## 2) Get your app secret

- [nexo.luzia.com/partners](https://nexo.luzia.com/partners)

## 3) Send a test request

```bash
curl -X POST "https://nexo-examples-py-v3me5awkta-ew.a.run.app/webhook/minimal" \
  -H "Content-Type: application/json" \
  -H "X-App-Secret: <your-shared-secret>" \
  -d '{"message":{"content":"hello"}}'
```

If that works, go to [Examples](examples.md) for Python, TypeScript, and cURL source code.

## Need your own hosted copy?

- Use [Quickstart](quickstart.md) and run:

```bash
gcloud auth login --update-adc
gcloud auth application-default login
PROJECT_ID=<your-project-id> PROJECT_NUMBER=<your-project-number> REGION=<your-region> make gcp-bootstrap
make deploy-examples
```

Need help: [mmm@luzia.com](mailto:mmm@luzia.com) (Mark MacMahon)

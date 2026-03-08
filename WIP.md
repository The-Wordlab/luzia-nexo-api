# Work In Progress

**Last Updated:** 2026-03-08
**Status:** Sprint 48 - Cloud Run deployment prep complete.

## Current state

1. Webhook documentation uses one canonical response envelope (schema_version, status, content_parts).
2. All webhook examples aligned (minimal, structured, advanced, hosted Python/TypeScript, 4 RAG examples).
3. **Terraform removed** - unified on Cloud Build for all deployments (RAG examples + demo-receiver).
4. **Bootstrap script fixed** - dynamic GCP project lookup (no hardcoded project number).
5. **Integration smoke test** - `scripts/integration-smoke.sh` validates Nexo + deployed webhook end-to-end.
6. **Hosting docs updated** - Cloud Build is the single deployment pattern.

## Verification

Executed successfully:
- `make test-all` (with local `.venv/bin` in PATH)
- `make docs-build`

## Next step

Deploy to Cloud Run:
1. `make gcp-bootstrap` (enable APIs, create Artifact Registry)
2. Create secrets in Secret Manager (WEBHOOK_SECRET, OPENAI_API_KEY)
3. `GCP_PROJECT_ID=luzia-nexo-api-examples make deploy-examples`
4. `make verify-examples`
5. Run smoke test: `./scripts/integration-smoke.sh --webhook-url https://nexo-news-rag-HASH.run.app`

## Quick links

- [README.md](README.md)
- [docs/index.md](docs/index.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/partner-api-reference.md](docs/partner-api-reference.md)
- [docs/hosting.md](docs/hosting.md)

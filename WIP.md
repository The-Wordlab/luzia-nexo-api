# Work In Progress

**Last Updated:** 2026-03-11
**Status:** Production-hardening pass complete (ADC + pgvector + scheduler indexing).

## Current state

1. Webhook documentation uses one canonical response envelope (schema_version, status, content_parts).
2. All webhook examples aligned (minimal, structured, advanced, hosted Python/TypeScript, 4 RAG examples).
3. **Terraform removed** - unified on Cloud Build for all deployments (RAG examples + demo-receiver).
4. **Bootstrap script fixed** - dynamic GCP project lookup (no hardcoded project number).
5. **Integration smoke test** - `scripts/integration-smoke.sh` validates Nexo + deployed webhook end-to-end.
6. **Hosting docs updated** - Cloud Build is the single deployment pattern.
7. **RAG production defaults switched** - Gemini via Vertex ADC by default, OpenAI override for development.
8. **Durable vectors live** - Cloud SQL Postgres + pgvector in Cloud Run RAG services.
9. **Automated indexing added** - Cloud Scheduler job script for all four RAG services.

## Verification

Executed successfully:
- `make test-all` (with local `.venv/bin` in PATH)
- `make docs-build`

## Next step

Operational checklist:
1. `make gcp-bootstrap` (enable APIs, create Artifact Registry)
2. Create secrets in Secret Manager (`WEBHOOK_SECRET`, `NEXO_PGVECTOR_DSN`, `FOOTBALL_DATA_API_KEY`, optional `OPENAI_API_KEY`)
3. Deploy RAG services: `GCP_PROJECT_ID=<id> GCP_REGION=<region> ./scripts/deploy-rag-examples.sh all`
4. Configure scheduler indexing: `GCP_PROJECT_ID=<id> GCP_REGION=<region> ./scripts/setup-rag-scheduler.sh all`
5. Verify health endpoints show `vector_store.backend=pgvector` and `durable=true`
6. Run smoke test: `./scripts/integration-smoke.sh --webhook-url <service-url>`

## Quick links

- [README.md](README.md)
- [docs/index.md](docs/index.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/partner-api-reference.md](docs/partner-api-reference.md)
- [docs/hosting.md](docs/hosting.md)

## Backlog (next hardening)

1. Add optional Cloud Run Jobs worker image path for ingest (in addition to HTTP scheduler mode) for fully private service topologies.
2. Add CI check to validate scheduler jobs exist and point to current deployed RAG URLs.
3. Remove temporary Cloud SQL authorized network entries after all operations are connector-only.

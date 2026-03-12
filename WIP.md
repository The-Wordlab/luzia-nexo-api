# Work In Progress

**Last Updated:** 2026-03-12
**Status:** Production-hardening pass complete (ADC + pgvector + scheduler indexing + worker jobs + setup UX).

## Current state

1. Webhook documentation uses one canonical response envelope (schema_version, status, content_parts).
2. All webhook examples aligned (minimal, structured, advanced, hosted Python/TypeScript, 4 RAG examples).
3. **Terraform removed** - unified on Cloud Build for all deployments (RAG examples + demo-receiver).
4. **Bootstrap script fixed** - dynamic GCP project lookup (no hardcoded project number).
5. **Integration smoke test** - `scripts/integration-smoke.sh` validates Nexo + deployed webhook end-to-end.
6. **Hosting docs updated** - Cloud Build is the single deployment pattern.
7. **RAG production defaults switched** - Gemini via Vertex ADC by default, OpenAI override for development.
8. **Durable vectors live** - Cloud SQL Postgres + pgvector in Cloud Run RAG services.
9. **Automated indexing added** - Cloud Scheduler endpoint-mode jobs for all four RAG services.
10. **Worker indexing mode added** - Cloud Run Jobs + Scheduler wiring for all four RAG services.
11. **Dev setup simplified** - `make setup-dev` installs Python/docs dependencies for a fresh checkout.
12. **Public dashboard URL docs aligned** - partner-facing docs now consistently point to `https://nexo.luzia.com` (no `/partners` path references).
13. **A2A rollout started** - `news-rag`, `sports-rag`, `travel-rag`, and `football-live` now publish `/.well-known/agent.json` and include `task`/`capability`/`artifacts` in webhook envelopes.

## Verification

Executed successfully:
- `make setup-dev`
- `make test-all`
- `make docs-build`
- `GCP_PROJECT_ID=luzia-nexo-api-examples make check-rag-scheduler`
- `GCP_PROJECT_ID=luzia-nexo-api-examples make check-rag-worker-scheduler`
- `gcloud run jobs execute nexo-rag-{news,sports,travel,football}-worker --wait` (all successful)
- `make test-rag-examples`

## Next step

Operational checklist:
1. `make gcp-bootstrap` (enable APIs, create Artifact Registry)
2. Create secrets in Secret Manager (`WEBHOOK_SECRET`, `NEXO_PGVECTOR_DSN`, `FOOTBALL_DATA_API_KEY`, optional `OPENAI_API_KEY`)
3. Deploy RAG services: `GCP_PROJECT_ID=<id> GCP_REGION=<region> ./scripts/deploy-rag-examples.sh all`
4. Choose indexing mode:
   - Endpoint mode: `GCP_PROJECT_ID=<id> GCP_REGION=<region> ./scripts/setup-rag-scheduler.sh all`
   - Worker mode: `GCP_PROJECT_ID=<id> GCP_REGION=<region> SCHEDULER_RUNNER_SA=<sa> ./scripts/setup-rag-worker-scheduler.sh all`
5. Verify scheduler drift:
   - Endpoint mode: `GCP_PROJECT_ID=<id> GCP_REGION=<region> ./scripts/check-rag-scheduler.sh endpoint`
   - Worker mode: `GCP_PROJECT_ID=<id> GCP_REGION=<region> ./scripts/check-rag-scheduler.sh worker`
6. Verify health endpoints show `vector_store.backend=pgvector` and `durable=true`
7. Run smoke test: `./scripts/integration-smoke.sh --webhook-url <service-url>`

## Quick links

- [README.md](README.md)
- [docs/index.md](docs/index.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/partner-api-reference.md](docs/partner-api-reference.md)
- [docs/hosting.md](docs/hosting.md)

## Backlog (next hardening)

1. Add worker-job execution observability (structured logs + simple success/failure dashboard query snippets).
2. Add one-command bootstrap for Scheduler runner service account IAM grants (`run.jobs.run`, `iam.serviceAccountTokenCreator` where required).
3. Keep Cloud SQL access connector-only and periodically verify no temporary authorized networks reappear.
4. Add a dedicated requirements lock strategy for examples to reduce version churn across mixed requirements files.
5. Add a docs lint/check that fails CI if public docs reintroduce non-canonical dashboard paths.
6. Add an internal-only A2A conformance gate that validates all webhook examples for: `agent.json`, sync lifecycle, stream lifecycle, artifact-only completion, and structured failures.
7. Add explicit cancellation coverage (`task.canceled`) to streaming examples and contract tests.
8. Publish schema-level examples for `cards` and `actions` mapped to A2A-style artifacts so partner implementations stay consistent.
9. Add compatibility tests for mixed webhook payloads (classic Nexo envelope + A2A optional fields) to prevent regressions.
10. Define an internal rollout checklist for advancing A2A features without exposing implementation status in public docs.

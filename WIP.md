# Work In Progress

**Last Updated:** 2026-04-26
**Status:** Post-migration. External runtime integration guide shipped. Knowledge Packs docs shipped. World Cup consolidated into worldcup-server.

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
13. **A2A rollout started** - `news-rag`, `sports-rag`, and `travel-rag` now publish `/.well-known/agent.json` and include `task`/`capability`/`artifacts` in webhook envelopes.
14. **World Cup migration direction clarified** - World Cup-specific product/runtime architecture should consolidate into `worldcup-server`; this repo should keep only reusable generic patterns.
15. **External app auth bridge documented as phase-1 internal contract** - public docs now explain the Nexo-owned login plus one-time callback model for externally hosted apps. The Nexo-side auth-handoff create/exchange and auth continuation slices are now real for Luzia-owned apps, but public docs should still treat this as narrow/internal availability rather than a broad self-serve partner API.
16. **Connected companion proving slice now exists in Nexo** - the runtime half of the hosted-app proof is no longer hypothetical: Nexo can now accept browser-facing companion turns from a Micro App surface, resolve an approved linked Connected App companion, and reload the same Nexo-owned companion thread context. The next public-doc truth is no longer "handoff is purely planned" - it is "phase-1 internal, not yet broadly enabled".

## What shipped recently

- External runtime integration guide added (`docs/external-runtime-integration.md`):
  account linking flow, capability sync, context summaries, context bundles,
  Knowledge Pack sync, worker/job topology, companion services (including
  Ask Expert pattern), and end-to-end lifecycle reference
- Partner API reference updated with external sync endpoints and cross-links to
  the new guide
- mkdocs.yml navigation updated with External Runtime Integration entry
- football-live example fully removed (code, docs, tests, CI, docker-compose)
- Knowledge Packs developer guide added (`docs/knowledge-packs.md`)
- MCP tools table updated with 6 KP tools
- World Cup references scrubbed from platform docs (lives in worldcup-server now)
- demo-apps.json cleaned (football-live entry and sports-rag deep_dives removed)

## Next

- Update docs when the new Nexo provisioning endpoint ships
  (`POST /api/micro-apps/provision`) - this replaces the 15-call setup pattern
- Update MCP docs when `provision_app` MCP tool ships
- Keep the external app auth bridge page truthful as the implementation lands:
  the Nexo-side auth-handoff endpoints are now real for the internal Luzia
  path, but public docs should not present them as a broad public partner API
- Keep the auth bridge doc explicit that:
  - linked Connected App companion ingress is already proven
  - create/exchange plus auth continuation now exists internally
  - user-facing hosted login entry and guest-adoption continuity are still the
    remaining proving work
- Consider adding a "Getting Started: Create Your First App" guide that shows
  the one-call provisioning flow
- Keep operational RAG services healthy (news, sports, travel on Cloud Run)

## Quick links

- [README.md](README.md)
- [docs/index.md](docs/index.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/partner-api-reference.md](docs/partner-api-reference.md)
- [docs/hosting.md](docs/hosting.md)

## Recent (2026-04-24)

15. **World Cup migration completed** - football-live example fully removed
    (code, docs, tests, CI, docker-compose). `worldcup-server` is now the
    canonical home for World Cup product and Nexo-backed app architecture.
    This repo keeps only reusable generic patterns.
16. **Landing page rewritten** - externally focused, two clear paths (Connected
    Apps / Personalized Apps), no internal architecture details exposed.

## Recent (2026-04-20)
14. **Knowledge Packs documentation added** - full developer guide at
    `docs/knowledge-packs.md` covering packs, datasets, records, sources,
    projections, REST API examples, MCP tools, sync workflow, and ownership
    model. MCP tools table updated in `docs/mcp.md`. Navigation and index
    updated with Knowledge Packs as a third developer lane.

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

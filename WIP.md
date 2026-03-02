# Work In Progress

**Last Updated:** 2026-03-02 14:55 CET
**Last Synced:** 2026-03-02 14:55 CET
**Status:** Sprint API-3 in progress.

## Current state

1. Hosted examples are now deployable as two Cloud Run services: `nexo-examples-py` and `nexo-examples-ts`.
2. Both hosted services expose health endpoints and enforce shared secret auth via `X-App-Secret`.
3. Live deployment and verification succeeded in `luzia-nexo-api-examples` using `make deploy-examples` and `make verify-examples`.
4. Demo receiver is deployed independently as `nexo-demo-receiver`.
5. Partner onboarding flow is documented in `docs/onboarding.md` with hosted usage and self-deploy paths.

## Latest completed sprint

Sprint API-2 complete: API-005, API-006, API-009, API-010 delivered.

## Active sprint plan

Sprint API-3 - Deployment Automation: IN PROGRESS

Items:
- API-011: Terraform one-command deployment flow (in_progress)
- API-012: TypeScript hosted lane (done)
- API-013: Hosted Python + TypeScript with shared auth and verification (done)

## Execution notes

1. Keep this track isolated from `luzia-nexo` sprint execution.
2. Maintain clean separation from production infrastructure.
3. Keep docs and implementation synchronized on each completion.

## Quick links

- [docs/backlog.md](docs/backlog.md)
- [docs/current-sprint.md](docs/current-sprint.md)
- [docs/system-overview.md](docs/system-overview.md)
- [docs/quickstart.md](docs/quickstart.md)

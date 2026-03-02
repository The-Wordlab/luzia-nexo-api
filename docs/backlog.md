# Backlog

Ordered by execution priority. **Updated:** 2026-03-02 14:55 CET
**Last Synced:** 2026-03-02 14:55 CET

## Operating model

1. Pull highest-priority unblocked `Now` item.
2. If blocked, pull next unblocked item immediately.
3. Keep docs synchronized (`WIP`, `current-sprint`, `backlog`) on every completion.
4. Prefer minimal, runnable vertical slices over broad abstractions.

## Now

### API-011 - Terraform one-command deployment for demo receiver

- Problem: Infra and service deploy steps are split between Terraform and manual Cloud Run commands.
- Outcome: single documented flow provisions infra and deploys receiver artifact.
- Acceptance checks:
  - Terraform apply provisions required resources.
  - `docs/quickstart.md` includes end-to-end deploy steps.
  - Runbook includes rollback and teardown steps.
- Dependencies: none.
- Owner lane: platform.
- Exit rule: clean bootstrap path for new forks.

## Next

### API-014 - Shared secret sync helper with `luzia-nexo`

- Problem: hosted example services require `EXAMPLES_SHARED_API_SECRET`, and drift from `luzia-nexo` app webhook secrets causes demo confusion.
- Outcome: helper script documents and validates a single shared secret workflow across repos.
- Acceptance checks:
  - script or guide for syncing/rotating shared secret.
  - explicit header contract (`X-App-Secret`) documented for both hosted services.
  - verification command passes after sync.
- Dependencies: API-012, API-013.
- Owner lane: platform/docs.
- Exit rule: one repeatable secret workflow for demo operators.

## Deferred

| ID | Reason |
|---|---|
| API-D1 | SDK publication deferred until contract stability is proven with examples and receiver. |
| API-D2 | Additional hosted demo environments deferred (Cloud Run first, platform-neutral core). |

## Recently completed

1. API-005 complete: structured webhook tier shipped with tests.
2. API-006 complete: advanced webhook tier shipped with tests.
3. API-009 complete: JavaScript SDK migrated and tests running in this repo.
4. API-010 complete: CI now validates demo receiver plus Python and TypeScript examples.
5. API-012 complete: hosted TypeScript service deployed on Cloud Run with health and auth checks.
6. API-013 complete: hosted Python/TypeScript services added with shared `X-App-Secret` auth and live verification (`make verify-examples`).
7. API-015 complete: partner onboarding guide added (`docs/onboarding.md`) and linked from README.

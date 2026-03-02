# Current Sprint: Sprint API-3 - Deployment Automation

**Status:** in_progress
**Updated:** 2026-03-02 14:55 CET
**Last Synced:** 2026-03-02 14:55 CET

Execution source of truth: `docs/backlog.md` (`Now` section).

## Sprint objective

Automate fork-to-deploy setup so a partner can clone this repo, provision GCP once, and deploy demo receiver plus hosted examples with minimal manual steps.

## In scope now

| ID | Area | Task | Owner | Status | Acceptance Artifact |
|---|---|---|---|---|---|
| API-011 | Platform / Deploy | Terraform one-command deployment for demo receiver | platform-dev | in_progress | documented bootstrap + apply flow |
| API-012 | Platform / Examples | TypeScript hosted examples lane (`nexo-examples-ts`) | platform-dev | done | deployable TypeScript service + health endpoint |
| API-013 | Platform / Examples | Hosted Python + TypeScript examples with shared auth | platform-dev | done | deploy scripts + live verification |

## Out of scope this sprint

1. Production infra coupling with ECS/AWS stacks.
2. Dashboard feature development inside `luzia-nexo`.
3. Partner SDK publication pipeline.

## Working loop

1. Pull highest-priority unblocked item.
2. Red-green-refactor for code changes.
3. Run targeted tests first, then broader checks.
4. Update backlog, sprint doc, and WIP together.

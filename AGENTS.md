# AGENTS.md - luzia-nexo-api

This is the operating guide for AI agents and engineers in this repository.

## Mission

Build and maintain a clean, partner-facing integration repository that is:

1. Separate from production runtime infrastructure
2. Easy for partners to run and fork
3. Focused on examples, SDK assets, and hosted demo receiver patterns

## Scope boundaries

In scope:
- `examples/` (minimal, structured, advanced progression)
- `demo-receiver/` service and tests
- `infra/terraform/gcp-demo-receiver/`
- `docs/` for partner integration and migration
- `sdk/` packaging assets

Out of scope:
- ECS/AWS production runtime implementation
- Dashboard feature implementation inside `luzia-nexo`
- Replit-specific setup and platform-lock artifacts

## Working loop (strict)

1. Read `WIP.md`, `docs/current-sprint.md`, `docs/backlog.md`
2. Pull highest-priority unblocked `Now` item
3. Execute with TDD (RED -> GREEN -> REFACTOR)
4. Run targeted tests, then relevant broader gates
5. Update `WIP`, `current-sprint`, `backlog` in the same cycle
6. If blocked, pull next unblocked item immediately
7. At sprint close, update `docs/latest-sprint.md` and promote next work

## Status vocabulary

Use only:
- `planned`
- `in_progress`
- `blocked`
- `done`

## Test and quality gates

### Demo receiver

```bash
cd demo-receiver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### Terraform (when touched)

```bash
cd infra/terraform/gcp-demo-receiver
terraform fmt -check
terraform validate
```

### Examples

- Keep examples runnable with minimal dependencies
- Add tests for structured and advanced tiers when behavior goes beyond trivial echo

## Documentation rules

1. Keep docs lean and operational.
2. Keep one source of truth per topic.
3. Keep migration tables explicit and current.
4. Include `Last Updated` and `Last Synced` with timestamp in core operational docs.

## Non-negotiables

1. No Replit-specific files (`.replit`, `replit.nix`, etc.)
2. No committed local env/caches (`.venv`, `__pycache__`, `.pytest_cache`)
3. No duplication without progression value
4. Keep canonical API contract in `luzia-nexo`; this repo consumes it

## Sprint close checklist

1. Mark sprint tasks `done` in `docs/current-sprint.md` and `docs/backlog.md`
2. Write/update `docs/latest-sprint.md`
3. Promote next-ready items in backlog
4. Sync `WIP.md`
5. Run tests for changed scope

## .claude notes

Lean agent-team assets live under `.claude/` in this repo.
They should remain scoped to this repository's mission.

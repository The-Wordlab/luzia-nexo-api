---
name: fix-actions
description: Diagnose and fix GitHub Actions failures for this repository
allowed-tools: Bash, Read, Edit, Glob, Grep, Write
---

# Fix GitHub Actions Failures (luzia-nexo-api)

## 1. Inspect recent runs

```bash
gh run list --limit 10
```

## 2. Inspect failed logs

```bash
gh run view <run-id> --log-failed
```

## 3. Common fixes

1. Demo receiver test failures - fix code/tests in `demo-receiver/`.
2. Terraform validation failures - run `terraform fmt` and fix invalid config.
3. Docs drift - sync `WIP`, `docs/current-sprint`, `docs/backlog`, `docs/latest-sprint`.

## 4. Verify locally

```bash
cd demo-receiver && . .venv/bin/activate && pytest -q
```

Run Terraform checks if infra changed.

## 5. Report

Provide:
- Root cause
- Files changed
- Verification status

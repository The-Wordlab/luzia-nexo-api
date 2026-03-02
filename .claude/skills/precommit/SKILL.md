---
name: precommit
description: Run repository quality gates and fix straightforward issues
allowed-tools: Bash, Read, Edit, Glob, Grep, Write
---

# Pre-Push Gate (luzia-nexo-api)

Run checks in order and fix issues before push.

## 1. Demo receiver tests

```bash
cd demo-receiver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## 2. Terraform checks (if infra changed)

```bash
cd infra/terraform/gcp-demo-receiver
terraform fmt -check
terraform validate
```

## 3. Basic repository hygiene

- Ensure no `.venv`, `__pycache__`, `.pytest_cache`, `.replit`, `replit.nix` are introduced.
- Ensure docs reflect actual sprint/backlog state.

## 4. Report

Summarize pass/fail and what was fixed.
If all checks pass, state readiness to commit.

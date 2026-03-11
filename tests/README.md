# Test Layout

This repository has three main test surfaces:

1. Example-level tests (closest to implementation)
- Location: `examples/**/test_*.py`, `examples/**/test-*.mjs`
- Coverage: endpoint behavior, payload contracts, signing, cards/actions, worker-safe ingest flows.

2. Contract suite (cross-example consistency)
- Location: `tests/contracts/`
- Coverage: canonical Nexo webhook request/response/signature schema across all examples.

3. Hosted/service smoke tests
- Location: `examples/hosted/**/tests`
- Coverage: auth and route behavior for hosted reference services.

## Recommended commands

```bash
make setup-dev

# Core local confidence gate
make test-examples
make test-rag-examples
make test-contracts
make test-hosted-examples

# Full repo confidence gate
make test-all
```

## CI mapping

- `.github/workflows/ci.yml` runs python example suites, node suites, and docs build.
- `.github/workflows/ops-scheduler-check.yml` verifies scheduler drift against deployed services/jobs when GCP credentials are configured.

# Work In Progress

**Last Updated:** 2026-03-05
**Status:** Documentation and example contract alignment complete.

## Current state

1. Webhook documentation now uses one canonical response envelope:
   - `schema_version`
   - `status`
   - `content_parts` (or `cards` / `actions`)
2. Legacy `reply`-style webhook response examples were removed from docs and webhook examples.
3. All webhook examples (minimal, structured, advanced, hosted Python, hosted TypeScript) now return the same rich envelope.
4. SDK docs and SDK client tests were updated to match current auth/base URL behavior.

## Verification

Executed successfully:
- `make test-all` (with local `.venv/bin` in PATH)
- `make docs-build`

## Next step

Deploy refreshed examples to Cloud Run after commit:
- `make deploy-examples`
- `make verify-examples`

## Quick links

- [README.md](README.md)
- [docs/index.md](docs/index.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/partner-api-reference.md](docs/partner-api-reference.md)
- [docs/hosting.md](docs/hosting.md)

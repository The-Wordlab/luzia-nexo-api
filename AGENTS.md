# AGENTS.md - luzia-nexo-api

This file defines the operating contract for contributors and AI agents in this repository.

## Repository purpose

`luzia-nexo-api` is the integration repository for Nexo.

It exists to provide:
- runnable webhook and API examples
- concise public integration documentation
- optional hosted example services

## Architecture language (required)

Use this target architecture wording in public docs and diagrams:

1. End user interacts with `Luzia Backend`
2. Luzia delegates partner connection handling to `Nexo Agent Runtime`
3. Nexo calls partner webhook endpoints

Webhook responses must clearly show both supported modes:
- traditional JSON response
- SSE streaming response

## Public documentation contract

Public docs must be simple, professional, and integration-first.

Required style:
- show fastest path first (first successful request)
- keep pages short and actionable
- prefer copy-paste commands and minimal code snippets
- link to examples instead of repeating long explanations

Do not include in public docs:
- internal planning/process text
- sprint/backlog language
- internal governance notes
- internal-only service details unless required for integration

## Source-of-truth and duplication rules

1. Docs site is the source of truth for setup and support links:
   - `https://the-wordlab.github.io/luzia-nexo-api/`
2. Example apps (`/info`, `/`) should point to docs site, not duplicate support metadata.
3. Avoid repeating the same setup text across multiple docs pages.

## Scope boundaries

In scope:
- `examples/`
- `examples-hosted/`
- `docs/`
- `sdk/`
- `infra/terraform/`

Out of scope:
- production ECS/AWS runtime implementation
- dashboard feature implementation in `luzia-nexo`

## Quality gates

Before pushing:

```bash
make docs-build
make test-examples
make test-hosted-examples
```

If a command cannot run in the current shell, document exactly what was not run and why.

## Clarification rule

If intent is ambiguous, ask a short clarification question before broad documentation or structural rewrites.

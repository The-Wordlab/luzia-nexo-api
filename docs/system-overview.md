# System Overview

`luzia-nexo-api` is a partner integration repository that houses:

1. Runnable webhook/proactive API examples for partners.
2. A dedicated demo receiver service for hosted webhook testing.
3. Deployment assets for isolated Cloud Run operation.
4. SDK assets that consume the canonical contract from `luzia-nexo`.

## Separation contract

- Canonical API specification remains in `luzia-nexo`.
- This repository must not include production ECS/AWS runtime infrastructure.
- This repository must remain platform-neutral for local execution and forking.

## Deploy resource naming

1. `nexo-demo-receiver` for the dedicated demo receiver service.
2. `nexo-examples-py` for hosted Python example endpoints.
3. `nexo-examples-ts` for hosted TypeScript example endpoints.
4. `nexo-examples-runtime` for runtime service account identity.

## Progression model for examples

1. `minimal` - simplest runnable webhook server.
2. `structured` - contract-aware handling with validation and tests.
3. `advanced` - realistic extension points, idempotency, retries.

## Hosted examples contract

Hosted Cloud Run services expose public health checks and secret-gated example endpoints.

1. Public health:
   - `GET /health`
2. Protected endpoints:
   - Header: `X-App-Secret: <shared-secret>`
   - Alternate: `Authorization: Bearer <shared-secret>`
3. Shared secret source:
   - `EXAMPLES_SHARED_API_SECRET` in both hosted deploy env files.
4. Discovery surface:
   - `GET /` and `GET /info` return endpoint catalog.
   - HTML default for browser usage, JSON via `?format=json` or `Accept: application/json`.
   - Includes repository link: `https://github.com/The-Wordlab/luzia-nexo-api`.
   - Includes partner portal link for API secret provisioning: `https://nexo.luzia.com/partners`.

# Hosted Nexo Examples - TypeScript

Cloud Run deployable Node service exposing hosted TypeScript example endpoints.

Endpoints:
- `GET /`
- `GET /info`
- `GET /health`
- `POST /webhook/minimal`
- `POST /partner/proactive/preview`

Auth:
- Shared secret required on non-health endpoints via `X-App-Secret` or `Authorization: Bearer <secret>`
- Env var: `EXAMPLES_SHARED_API_SECRET`

Run locally:

```bash
EXAMPLES_SHARED_API_SECRET=dev-secret node server.mjs
```

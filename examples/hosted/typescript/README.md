# Hosted Nexo Examples - TypeScript

Cloud Run deployable Node service exposing hosted TypeScript example endpoints.

Profile context note:
- Current stable profile field is `profile.locale`.
- Expanded consented profile fields will be added to stable docs over time.

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

Run with Docker:

```bash
docker build -t nexo-examples-ts .
docker run --rm -p 8080:8080 -e EXAMPLES_SHARED_API_SECRET=dev-secret nexo-examples-ts
```

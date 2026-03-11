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
- By default, hosted endpoints are open for easier demo onboarding.
- Optional hardening: set `EXAMPLES_SHARED_API_SECRET` to require `X-App-Secret` or `Authorization: Bearer <secret>` on webhook/proactive routes.

Run locally:

```bash
node server.mjs
```

Run with Docker:

```bash
docker build -t nexo-examples-ts .
docker run --rm -p 8080:8080 nexo-examples-ts
```

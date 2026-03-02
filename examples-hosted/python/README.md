# Hosted Nexo Examples - Python

Cloud Run deployable service exposing hosted Python example endpoints.

Endpoints:
- `GET /`
- `GET /info`
- `GET /health`
- `POST /webhook/minimal`
- `POST /webhook/structured`
- `POST /webhook/advanced`
- `POST /partner/proactive/preview`

Auth:
- Shared secret required on non-health endpoints via `X-App-Secret` or `Authorization: Bearer <secret>`
- Env var: `EXAMPLES_SHARED_API_SECRET`

Run locally:

```bash
EXAMPLES_SHARED_API_SECRET=dev-secret uvicorn app.main:app --reload --port 8080
```

Run with Docker:

```bash
docker build -t nexo-examples-py .
docker run --rm -p 8080:8080 -e EXAMPLES_SHARED_API_SECRET=dev-secret nexo-examples-py
```

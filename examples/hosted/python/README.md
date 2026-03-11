# Hosted Nexo Examples - Python

Cloud Run deployable service exposing hosted Python example endpoints.

Profile context note:
- Current stable profile field is `profile.locale`.
- Expanded consented profile fields will be added to stable docs over time.

Endpoints:
- `GET /`
- `GET /info`
- `GET /health`
- `POST /webhook/minimal`
- `POST /webhook/structured`
- `POST /webhook/advanced`
- `POST /partner/proactive/preview`

Auth:
- By default, hosted endpoints are open for easier demo onboarding.
- Optional hardening: set `EXAMPLES_SHARED_API_SECRET` to require `X-App-Secret` or `Authorization: Bearer <secret>` on webhook/proactive routes.

Run locally:

```bash
uvicorn app.main:app --reload --port 8080
```

Run with Docker:

```bash
docker build -t nexo-examples-py .
docker run --rm -p 8080:8080 nexo-examples-py
```

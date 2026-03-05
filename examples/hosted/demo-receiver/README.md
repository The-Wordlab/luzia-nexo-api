# Demo Receiver

Minimal hosted webhook receiver for demos.

## Endpoints

- `POST /v1/ingest/{demo_key}` - accept and store event payloads
- `GET /v1/events/{demo_key}` - retrieve recent events
- `GET /health` - liveness

## Safety defaults

- Demo-key format validation
- Basic field redaction for token/secret-like keys
- Event retention cap and TTL

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Test

```bash
pytest -q
```

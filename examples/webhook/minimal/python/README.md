# Minimal Webhook - Python

Smallest webhook contract implementation.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8080
```

## Test

```bash
pytest -q
```

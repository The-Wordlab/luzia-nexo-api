# Minimal Webhook - Python

Smallest webhook contract implementation.

Includes optional HMAC signature verification when `WEBHOOK_SECRET` is set.

Profile context:
- Today, treat `profile.locale` as the primary stable profile field.
- More consented profile fields will be added to the stable contract in future updates.

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

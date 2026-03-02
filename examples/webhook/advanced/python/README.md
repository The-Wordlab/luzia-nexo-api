# Advanced Webhook - Python

Demonstrates connector-style action routing, idempotency, and retry-aware responses.

Profile context:
- Treat `profile.locale` as stable today and parse other profile fields defensively.
- Expanded consented profile fields will be documented as they become stable.

Run:

```bash
python server.py
```

Test:

```bash
pytest -q test_advanced.py
```

# Advanced Webhook - Python

Demonstrates connector-style action routing, idempotency, and retry-aware responses.

## Request format

Nexo sends an A2A Message-shaped payload with user text in `message.parts`
and metadata in `message.metadata`. The legacy flat shape is also accepted
for backward compatibility.

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

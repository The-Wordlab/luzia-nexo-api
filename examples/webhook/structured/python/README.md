# Structured Webhook - Python

Adds profile-aware replies, locale handling, and optional `cards` hints.

## Request format

Nexo sends an A2A Message-shaped payload with user text in `message.parts`
and profile/locale in `message.metadata`. The legacy flat shape is also
accepted for backward compatibility.

Profile context:
- This example uses `profile.locale` and optional profile fields when present.
- The stable profile contract will expand over time as more consented fields are promoted.

Run:

```bash
python server.py
```

Test:

```bash
pytest -q test_structured.py
```

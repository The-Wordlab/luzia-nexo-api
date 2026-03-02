# Examples

Partner integration examples organized by progression level.

## Webhook progression

1. `webhook/minimal` - smallest runnable implementation.
2. `webhook/structured` - profile-aware and structured payload handling.
3. `webhook/advanced` - connector actions, idempotency, and retry behavior.

## Proactive API examples

`partner-api/proactive` contains outbound API usage examples.

## Test coverage

- `webhook/minimal/python` - `pytest`
- `webhook/structured/python` - `pytest`
- `webhook/advanced/python` - `pytest`
- `webhook/minimal/typescript` - `node --test`

Run all example tests from repo root:

```bash
make test-examples
```

## Scope rules

- No Replit-specific files.
- No committed virtual environments or cache artifacts.
- Keep examples intentionally differentiated by complexity.

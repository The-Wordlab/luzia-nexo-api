# CDC (Consumer-Driven Contract) Tests

These tests define and enforce the webhook contract between **Nexo** (the webhook caller) and **partner webhook examples** (the receivers).

## What are CDC tests?

Consumer-Driven Contract testing ensures the *consumer* (Nexo) and *providers* (partner webhooks) agree on a shared interface. If either side drifts, a test fails before it breaks production.

```
Nexo (consumer) ──POST──> Partner Webhook (provider)
      │                           │
      │   NexoWebhookRequest      │
      │──────────────────────────>│
      │                           │
      │   NexoWebhookResponse     │
      │<──────────────────────────│
      │                           │
      └── CDC tests validate both sides
```

## Running the tests

From the `tests/contracts/` directory, activate a Python environment with `fastapi`, `httpx`, `pydantic`, and `pytest-asyncio` installed:

```bash
# Using the minimal example's venv (works for most tests)
source ../../examples/webhook/minimal/python/.venv/bin/activate
pytest -v

# Or install deps directly
pip install fastapi httpx pydantic pytest pytest-asyncio anyio
pytest -v
```

For the RAG contract tests, you also need `litellm` and `feedparser`. If these are not installed, those tests are automatically skipped.

```bash
# Full suite including RAG examples
pip install litellm feedparser beautifulsoup4
pytest -v
```

## Test files

| File | What it tests |
|---|---|
| `nexo_webhook_contract.py` | Contract definitions (Pydantic models + HMAC helpers) |
| `conftest.py` | Shared fixtures |
| `test_request_contract.py` | Validates canonical Nexo request payloads against the schema |
| `test_response_contract.py` | Validates each example's response against the schema |
| `test_signature_contract.py` | Validates HMAC signing format across all examples |
| `test_all_examples_comply.py` | Parameterized: runs all 5 examples through 7 compliance checks |

## The contract

### Request (what Nexo sends)

```json
{
  "event": "message.created",
  "message": { "content": "..." },
  "profile": { "display_name": "...", "locale": "en" },
  "thread": { "id": "thread-xxx" },
  "context": { "intent": "..." },
  "timestamp": "2026-03-01T12:00:00Z"
}
```

**Required:** `message` (always present, may have empty content)
**Optional:** all other fields — partners must handle their absence

**HMAC headers:**
- `X-Timestamp`: Unix timestamp string
- `X-Signature`: `sha256=HMAC(secret, "<timestamp>.<body_utf8>")`

### Response (what partners must return)

```json
{
  "schema_version": "2026-03",
  "status": "completed" | "error",
  "content_parts": [{ "type": "text", "text": "..." }],
  "cards": [...],
  "actions": [...]
}
```

**Required:** `schema_version`, `status`, `content_parts` (non-empty)
**Optional:** `cards`, `actions`, `metadata`

**Card shape:** `{ "type": "...", "title": "...", "subtitle": "...", "description": "...", "fields": [...], "badges": [...], "metadata": {...} }`
**Action shape:** `{ "id": "...", "label": "...", "url": "...", "style": "primary"|"secondary" }`

Extra fields in requests and responses are **always allowed** for forward compatibility.

## What the tests catch

| Violation | Caught by |
|---|---|
| Wrong `schema_version` | `test_response_contract.py`, `test_all_examples_comply.py` |
| Invalid `status` value (e.g. `"ok"`) | `test_response_contract.py`, `test_all_examples_comply.py` |
| Empty or missing `content_parts` | `test_response_contract.py`, `test_all_examples_comply.py` |
| Card missing `type` | `test_response_contract.py`, `test_all_examples_comply.py` |
| Action missing `id` or `label` | `test_response_contract.py`, `test_all_examples_comply.py` |
| Action with invalid `style` | `test_response_contract.py` |
| Wrong HMAC signing format | `test_signature_contract.py` |
| Example crashes on canonical request | `test_all_examples_comply.py` |
| Example crashes on minimal request | `test_all_examples_comply.py` |

## Updating the contract

When Nexo changes its payload format:

1. Update `nexo_webhook_contract.py` — the Pydantic models are the single source of truth
2. Run `pytest -v` — failing tests indicate which examples need updating
3. Update each failing example to comply with the new schema
4. Update `CANONICAL_REQUEST` in `nexo_webhook_contract.py` if the sample payload changes
5. Bump `CURRENT_SCHEMA_VERSION` if the schema version string changes

When adding a new webhook example:

1. Add an entry to `WEBHOOK_EXAMPLES` in `test_all_examples_comply.py`
2. Run `pytest test_all_examples_comply.py -v` to verify compliance

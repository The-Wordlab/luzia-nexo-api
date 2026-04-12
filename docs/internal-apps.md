# Internal Apps

Internal apps are first-party apps that live inside Nexo and call Nexo's own APIs instead of dispatching to an external webhook URL. They use the same request/response envelope as partner webhook apps - same payload, same card rendering, same SSE streaming - but the handler runs in-process as a Python function.

## When to use internal apps

Use the internal app pattern when:

- The app needs direct access to Nexo's database and services (not just HTTP APIs)
- The app is first-party (owned by the Nexo team, not a partner)
- You want the same conversation UX as webhook apps without deploying a separate service

Examples: the Micro App Builder (creates and manages Micro Apps through conversation), an analytics assistant, an admin tool.

For partner integrations that run on external infrastructure, use the [webhook contract](partner-api-reference.md) instead.

## Architecture

```
User message
  -> Conversation orchestrator
    -> mode == "internal"?
      YES -> internal_app_registry.get_internal_handler(app_id)
             -> handler(WebhookRequestPayload) -> RunResult
      NO  -> webhook dispatch (external HTTP POST)
```

Internal apps plug into the same orchestrator that routes webhook calls. The orchestrator checks `config_json.integration.mode` on the app model. When the mode is `"internal"`, it looks up a registered handler function instead of making an HTTP request.

## The contract

Internal handlers receive a `WebhookRequestPayload` and return a `RunResult`. This is the same payload that external webhooks receive.

```python
from app.schemas import RunResult, WebhookRequestPayload


async def my_handler(payload: WebhookRequestPayload) -> RunResult:
    """Handle a message for an internal app."""
    user_message = payload.message.content
    app_id = payload.app["id"]
    thread_id = payload.thread["id"]

    # Your logic here - call Nexo APIs, query the database, etc.
    reply = f"You said: {user_message}"

    return RunResult(
        reply_text=reply,
        source="internal",
        metadata={
            "cards": [],
            "actions": [],
        },
    )
```

### WebhookRequestPayload fields

The handler receives the full webhook payload:

- `message.content` - the user's message text
- `message.id`, `message.seq` - message identity and sequence number
- `app` - `{"id": "...", "name": "..."}` the app receiving the message
- `thread` - `{"id": "...", "customer_id": "..."}` the conversation thread
- `history_tail` - recent conversation history (up to 10 messages)
- `profile` - user profile data (when consent is granted)
- `tools`, `attachments`, `connectors` - optional context
- `timestamp` - ISO 8601 timestamp

### RunResult fields

| Field | Type | Description |
|---|---|---|
| `reply_text` | string | The assistant's response text. |
| `source` | string | Always `"internal"` for internal apps. |
| `metadata` | dict | Cards, actions, and other structured data. |
| `pending` | bool | Whether the response is still being processed. |
| `memory_candidates` | list | Optional memory extraction candidates. |

## Handler registration

Register your handler using the `internal_app_registry` module:

```python
from app.services.internal_app_registry import (
    register_internal_handler,
    deregister_internal_handler,
    list_registered_handlers,
)

# Register
register_internal_handler("your-app-uuid", my_handler)

# Check what's registered
print(list_registered_handlers())

# Remove (cleanup)
deregister_internal_handler("your-app-uuid")
```

The `app_identifier` is the string UUID of the app (`str(app.id)`). Registration is module-level and persists for the lifetime of the process.

## App configuration

The app must have `config_json.integration.mode` set to `"internal"`:

```json
{
  "integration": {
    "mode": "internal"
  }
}
```

This can be set via the dashboard or directly in the database. When the orchestrator encounters an app with mode `"internal"`, it bypasses all webhook dispatch logic and calls the registered handler.

If mode is `"internal"` but no handler is registered, the orchestrator raises an error. Always register your handler at app startup.

## Reference implementation: the Micro App Builder

The Micro App Builder is the first internal app and serves as the reference implementation. It is an agentic loop powered by LangGraph that creates, modifies, and queries Micro Apps through conversation.

### What makes it a good reference

1. **Same contract as webhooks** - receives `WebhookRequestPayload`, returns `RunResult`
2. **Agentic loop** - multi-step reasoning (classify intent, gather context, plan, confirm, execute, render)
3. **Direct API access** - calls Micro Apps APIs as function calls, not HTTP
4. **Rich responses** - returns cards, actions, and webview links alongside text

### Builder tools

The Builder wraps existing Micro Apps API functions as agent tools:

| Tool | Purpose | Wraps |
|---|---|---|
| `list_my_apps()` | Show user's existing apps | `GET /api/micro-apps` |
| `create_app(prompt)` | Plan and provision a new app | `template-plan` + `provision-from-template` |
| `add_record(app_id, table_key, values)` | Add a record | `POST /api/tables/{id}/records` |
| `modify_app(app_id, instruction)` | Plan and apply a schema change | `template-operation-plan` + `apply-operation` |
| `query_app(app_id, question)` | Answer questions from structured data | `context.md` + LLM reasoning |
| `show_app(app_id, surface)` | Return a chat card or webview link | `GET /api/micro-apps/{id}/surface` |

### Source locations

In the luzia-nexo repository:

- Registry: `backend/app/services/internal_app_registry.py`
- Orchestrator dispatch: `backend/app/modules/conversation/orchestrator.py` (search for `mode == "internal"`)
- Builder tools: `backend/app/modules/micro_apps/builder/tools.py`
- Builder agent: `backend/app/modules/micro_apps/builder/`

## Creating a new internal app

### Step 1: Create the app record

Create an app in the dashboard (or via the API) with integration mode set to `"internal"`. Note the app UUID.

### Step 2: Write the handler

```python
# backend/app/services/my_internal_app.py

from app.schemas import RunResult, WebhookRequestPayload


async def handle_message(payload: WebhookRequestPayload) -> RunResult:
    """Handle messages for my internal app."""
    user_input = payload.message.content

    # Example: echo with metadata
    return RunResult(
        reply_text=f"Received: {user_input}",
        source="internal",
        metadata={
            "cards": [
                {
                    "type": "info",
                    "title": "Echo",
                    "description": user_input,
                }
            ],
        },
    )
```

### Step 3: Register at startup

Add registration to your app's startup sequence:

```python
# In your startup/lifespan code
from app.services.internal_app_registry import register_internal_handler
from app.services.my_internal_app import handle_message

register_internal_handler("your-app-uuid", handle_message)
```

### Step 4: Test

Send a message to the app through the Nexo chat UI or via the API:

```bash
curl -X POST "https://nexo.luzia.com/api/responses" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello from the internal app",
    "app_id": "your-app-uuid",
    "stream": false
  }'
```

The orchestrator will route the message to your registered handler instead of making a webhook call.

## Comparison: internal vs webhook apps

| Aspect | Internal app | Webhook app |
|---|---|---|
| Request payload | `WebhookRequestPayload` | Same |
| Response | `RunResult` (Python) | JSON/SSE over HTTP |
| Hosting | In-process (same server) | External (Cloud Run, etc.) |
| Config mode | `"internal"` | `"webhook"` |
| Auth | No HTTP auth needed | HMAC-SHA256 signature |
| Use case | First-party Nexo features | Partner integrations |
| Latency | Sub-millisecond dispatch | Network round-trip |

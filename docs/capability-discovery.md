# Capability Discovery

Discover what apps and capabilities are available to your developer account, then use that information to route requests, load context, and link into UI surfaces.

## What the manifest is for

The capability manifest is a single endpoint that returns every app you can access - both Connected Apps (webhook-backed) and Personalized Apps (structured data apps managed by Nexo). Each entry describes the app's identity, what it can do (intents), where to fetch its full context, and how to reach its UI.

Use it when your runtime needs to:

- Enumerate available skills dynamically rather than hardcoding app IDs
- Route a user request to the right app based on intent matching
- Fetch an app's context for grounding an LLM call
- Deep link into an app's dashboard, runtime, or webview

## Fetch the manifest

**Prerequisites:** A developer key exchanged for a Bearer token. See [Developer Auth](developer-auth.md).

```bash
# Exchange your developer key for a JWT
TOKEN=$(curl -s -X POST "${NEXO_BASE_URL}/api/auth/key-exchange" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "nexo_uak_..."}' | jq -r '.access_token')

# Fetch the manifest
curl "${NEXO_BASE_URL}/api/capabilities/manifest" \
  -H "Authorization: Bearer ${TOKEN}"
```

The response contains a `version` string, a `generated_at` timestamp, and an `entries` array with one object per app.

## What each entry means

Every entry in the `entries` array represents one app:

| Field | What it tells you |
|---|---|
| `app_id` | The stable UUID you use to reference this app in other API calls. |
| `slug` | A human-friendly template key (Personalized Apps only). |
| `name` | The display name shown to users. |
| `family` | Whether this is a `"personalized_app"` or `"connected_app"`. |
| `initiative_key` / `initiative_role` | Optional grouping metadata when multiple apps form a shared initiative. |
| `owner_type` / `owner_label` | Whether the app is owned by a `"user"` or an `"org"`, and the org name if applicable. |
| `character` | The character identity associated with the app (Connected Apps only). Contains `character_id` and `character_name`. |
| `capability_summary` | A one-line description of what the app does. Useful for intent matching or displaying to users. |
| `intents` | A list of intent identifiers the app can handle (e.g. `"expense-tracker.create"`, `"sports.scores"`). |
| `context` | URLs for the app's context bundle: `markdown_url` (human-readable) and `json_url` (machine-readable). |
| `ui` | URLs for the app's surfaces: `dashboard_url`, `runtime_url`, `webview_url`, and optionally `public_app_url`. |

## Dynamic skill discovery

The manifest enables your runtime to discover skills at call time rather than maintaining a static registry.

## Initiative-shaped app families

Some product families are one initiative with multiple related apps or app
surfaces. In that case, the manifest is still the canonical discovery seam.

Use it like this:

1. fetch the manifest
2. group entries by `initiative_key`
3. within an initiative, choose the specific app by `initiative_role` and
   `intents`
4. use that entry's `context` and `ui` URLs for grounding and handoff

This avoids inventing a second registry for hybrid app families. If a product
family grows into multiple apps, `initiative_key` and `initiative_role` are the
grouping contract you should trust.

### Example: intent-based routing

```python
import httpx

def fetch_manifest(base_url: str, token: str) -> list[dict]:
    resp = httpx.get(
        f"{base_url}/api/capabilities/manifest",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()["entries"]

def find_app_for_intent(entries: list[dict], intent: str) -> dict | None:
    """Find the first app whose intents list contains a match."""
    for entry in entries:
        if any(intent in i for i in entry["intents"]):
            return entry
    return None

# Usage
entries = fetch_manifest(NEXO_BASE_URL, token)
app = find_app_for_intent(entries, "scores")
if app:
    print(f"Route to: {app['name']} ({app['app_id']})")
```

### Example: loading context for LLM grounding

Once you have identified the right app, fetch its context to ground your LLM call:

```python
def load_app_context(base_url: str, token: str, entry: dict) -> str:
    """Fetch the markdown context for an app."""
    url = f"{base_url}{entry['context']['markdown_url']}"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.text

context = load_app_context(NEXO_BASE_URL, token, app)
# Pass `context` as system prompt or reference material to your LLM
```

The JSON context (`context.json_url`) returns a structured representation including schema, sample data, and configuration - useful for programmatic consumers. The markdown context (`context.markdown_url`) is better for injecting directly into LLM prompts.

## Caching and freshness

The manifest is generated on each request from live data. For performance-sensitive runtimes, cache the response locally and refresh periodically (e.g. every 5 minutes) or when a user's app set changes.

The `generated_at` timestamp tells you when the snapshot was created. The `version` field tracks the manifest schema version and will increment when the response shape changes.

## Relationship to MCP

The [MCP Server](mcp.md) exposes the same app set as callable tools. The
manifest endpoint provides discovery metadata (intents, initiative grouping,
context URLs, UI links) that MCP tool definitions do not carry. Use the
manifest for planning and routing; use MCP for execution.

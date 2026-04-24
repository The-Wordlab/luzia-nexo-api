# Tutorial: Create a Personalized App from the Terminal

Build a fully structured app using natural conversation with an AI coding assistant.
No dashboard clicks, no REST calls, no schema design.

This is the same underlying creation grammar used by the dashboard Builder chat
inside `luzia-nexo`. Builder and MCP are two surfaces over the same creation
contract.

## Prerequisites

- A Nexo account
- A developer key (Dashboard → Profile → Developer Access)
- Claude Code installed (or any MCP client)

## Step 1: Connect

```bash
export NEXO_DEVELOPER_KEY=nexo_uak_...
export NEXO_BASE_URL=http://localhost:8000
claude mcp add --scope project --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"
```

Or run `bash scripts/connect-mcp.sh` from the repo root.

Verify the connection inside Claude Code with `/mcp` — you should see `nexo-mcp` listed with 11+ tools.

## Step 2: Create an app

Tell the agent what you want:

> "Create an expense tracker for a shared apartment. We split rent, utilities, groceries, and eating out."

**What happens behind the scenes:**

1. The agent calls `micro_apps__plan_app` with your prompt. Nexo returns a structured template:

    ```json
    {
      "status": "ok",
      "source": "template_engine",
      "template": {
        "name": "Shared Apartment Expenses",
        "archetype": "shared_expenses",
        "tables": [
          {
            "key": "expenses",
            "label": "Expenses",
            "fields": [
              { "key": "description", "label": "Description", "type": "text", "required": true },
              { "key": "amount", "label": "Amount", "type": "number", "required": true },
              { "key": "category", "label": "Category", "type": "select", "options": ["rent", "utilities", "groceries", "eating_out", "other"] },
              { "key": "paid_by", "label": "Paid by", "type": "text", "required": true },
              { "key": "date", "label": "Date", "type": "date", "required": true },
              { "key": "split", "label": "Split", "type": "number" }
            ]
          },
          {
            "key": "people",
            "label": "Roommates",
            "fields": [
              { "key": "name", "label": "Name", "type": "text", "required": true }
            ]
          }
        ],
        "views": [
          { "key": "all_expenses", "type": "list", "table_key": "expenses" },
          { "key": "by_category", "type": "cards", "table_key": "expenses" },
          { "key": "summary", "type": "summary", "table_key": "expenses" }
        ],
        "seed_records": [
          { "table_key": "expenses", "values": { "description": "April rent", "amount": 1200, "category": "rent", "paid_by": "Alice", "date": "2026-04-01", "split": 3 } }
        ]
      }
    }
    ```

2. The agent calls `micro_apps__provision_app` with the template. Nexo creates the app:

    ```json
    {
      "status": "ok",
      "app": { "id": "a1b2c3d4-...", "name": "Shared Apartment Expenses" },
      "tables_created": 2,
      "fields_created": 7,
      "views_created": 3,
      "records_created": 1
    }
    ```

Your app now exists with 2 tables, 7 fields, 3 views, and a seed record.

## Choosing the right path

Use the recommended prompt-driven path by default:

1. clarify the goal
2. `plan_app`
3. review
4. `provision_app`
5. inspect with `show_app` or `get_context`
6. evolve with `plan_operation` / `apply_operation`

Use `create_app` only when you intentionally want to start from an empty shell
with an exact schema in mind.

If planning or provisioning fails:

- surface the real provider / planner error
- retry the same step when retry makes sense
- do not silently switch to a different creation path
- do not hide the error behind deterministic fallback

## Step 3: Add data

> "Add: $120 groceries, paid by Alice, split 3 ways"

The agent calls `micro_apps__add_record`:

```json
{
  "app_id": "a1b2c3d4-...",
  "table_key": "expenses",
  "values": {
    "description": "Groceries",
    "amount": 120,
    "category": "groceries",
    "paid_by": "Alice",
    "date": "2026-04-12",
    "split": 3
  }
}
```

Response:

```json
{
  "status": "ok",
  "record": {
    "id": "rec-uuid-...",
    "values": { "description": "Groceries", "amount": 120, "category": "groceries", "paid_by": "Alice", "date": "2026-04-12", "split": 3 }
  }
}
```

## Step 4: Evolve the schema

> "Add a 'settled' checkbox field to track which expenses have been paid back"

The agent calls `micro_apps__plan_operation`:

```json
{
  "prompt": "Add a settled checkbox field to track which expenses have been paid back",
  "app_id": "a1b2c3d4-..."
}
```

Response:

```json
{
  "status": "ok",
  "source": "template_engine",
  "operation": {
    "kind": "add_field",
    "app_id": "a1b2c3d4-...",
    "table_key": "expenses",
    "field": {
      "key": "settled",
      "label": "Settled",
      "type": "boolean",
      "required": false
    }
  }
}
```

Then the agent calls `micro_apps__apply_operation` with the operation object:

```json
{
  "status": "ok",
  "kind": "add_field",
  "app_id": "a1b2c3d4-...",
  "table_id": "tbl-uuid-...",
  "resource_id": "fld-uuid-...",
  "resource_type": "field"
}
```

The new field is live. Existing records get `settled: null` by default.

## Step 5: Query your data

> "Show me all unsettled expenses over $50"

The agent calls `micro_apps__query_app`:

```json
{
  "app_id": "a1b2c3d4-...",
  "table_key": "expenses",
  "filters": [
    { "field": "amount", "op": "gte", "value": 50 },
    { "field": "settled", "op": "neq", "value": true }
  ],
  "sort": [{ "field": "amount", "direction": "desc" }]
}
```

Response:

```json
{
  "status": "ok",
  "records": [
    { "id": "rec-1", "values": { "description": "April rent", "amount": 1200, "category": "rent", "paid_by": "Alice", "settled": null } },
    { "id": "rec-2", "values": { "description": "Groceries", "amount": 120, "category": "groceries", "paid_by": "Alice", "settled": null } }
  ],
  "total": 2
}
```

## Step 6: Get the full picture

> "Show me a summary of everything"

The agent calls `micro_apps__get_context`:

```json
{
  "status": "ok",
  "markdown": "## Shared Apartment Expenses\nExpense tracker | 2 records | Last updated: Apr 12\n### expenses (7 fields, 2 records)\nFields: description (text, required), amount (number, required), category (select), paid_by (text, required), date (date, required), split (number), settled (boolean)\nRecent:\n- Apr 12: Groceries, $120.00, groceries (Alice)\n- Apr 1: April rent, $1200.00, rent (Alice)\n### people (1 field, 0 records)\nFields: name (text, required)",
  "app_count": 1,
  "total_records": 2
}
```

This compact markdown is designed for LLM context injection — the agent can use it to understand your data before answering follow-up questions.

## What you built

In 6 conversational turns:

- A 2-table app (expenses + roommates) with typed fields
- 3 views (list, cards, summary)
- Seed data from the template
- A custom boolean field added after creation
- Filtered and sorted queries
- A full-context markdown summary

The same app is visible in the Nexo dashboard at `https://nexo.luzia.com/dashboard` and can be accessed via the [REST API](micro-apps-api.md).

## Using other MCP clients

The same workflow works in any MCP client. The key steps are always:
1. Connect to `${NEXO_BASE_URL}/mcp` with your developer key
2. Ask the agent to plan an app
3. Review and provision
4. Evolve with operations

**Claude Desktop:** Add the MCP server in `~/Library/Application Support/Claude/claude_desktop_config.json` (see [connection guide](mcp.md#claude-desktop-macos--windows)). Then say "Create a meal planner" in a new conversation.

**Cursor:** Add the MCP server in Settings -> MCP (see [connection guide](mcp.md#cursor)). Use the chat panel to describe apps.

**Codex / Windsurf:** Connect using the same HTTP transport URL and header. The tool sequence (`plan_app` -> `provision_app` -> `show_app` -> `plan_operation` -> `apply_operation`) is identical across all clients.

**Tip:** For richer apps, reference the [available primitives](mcp.md#app-building-primitives) in your prompt: "Create a training plan with a HeroCard daily view, milestones, and a progress_ratio metric."

If the app needs reference data or deterministic derived outputs, add a
follow-through step with [Knowledge Packs](knowledge-packs.md) instead of
trying to force everything into normal app records. If the app needs an owned
hosted domain, use the app's `Connect Website` / authorized-domain flow after
creation. Use public share only for temporary or revocable access.

If the app needs a custom frontend beyond the default Nexo runtime:

- keep Nexo as the backend/system of record
- decide whether you want:
  - a traditional `webapp`
  - a `webview_optimized` surface for native wrappers or compact standalone use
- publish the static frontend to Drophere by default unless another host is
  chosen explicitly
- prefer a Nexo vanity/origin launch path for ordinary authenticated web users
- use an explicit bootstrap/launch contract for native or true external launch

Quick ladder:

1. stay in default Nexo runtime if it already solves the product need
2. attach a custom frontend only when the UI actually needs more control
3. choose:
   - `webapp` for normal full-page web
   - `webview_optimized` for native-wrapper or compact standalone use
4. keep Nexo as the canonical backend
5. keep client-side JavaScript thin and presentation-focused

Quick rule:

- use normal app tables for user-entered workflow state
- use Knowledge Packs for reference datasets, freshness tracking, and
  deterministic projections like standings or leaderboards

Client-side JavaScript is a good fit for:

- local UI state
- progress rings and charts
- grouped summaries over already-fetched records
- sheets, tabs, drawers, and optimistic UX

Move the logic into backend contracts and/or Knowledge Packs when it becomes:

- canonical across clients
- based on reference data
- tied to sync/freshness
- a durable derived output that multiple surfaces should agree on

## Next steps

- [Personalized Apps API](micro-apps-api.md) -- full REST reference
- [MCP Server](mcp.md) -- all 11 available tools, connection guides, and app-building primitives
- [Agent Interop](agent-interop.md) -- MCP and A2A protocol details

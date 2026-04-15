# Tutorial: Create a Personalized App from the Terminal

Build a fully structured app using natural conversation with an AI coding assistant.
No dashboard clicks, no REST calls, no schema design.

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

## Next steps

- [Personalized Apps API](micro-apps-api.md) -- full REST reference
- [MCP Server](mcp.md) -- all 11 available tools
- [Agent Interop](agent-interop.md) -- MCP and A2A protocol details

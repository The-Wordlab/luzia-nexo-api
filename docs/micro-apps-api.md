# Personalized Apps API

Internally, Nexo still uses the technical term **micro apps**. In customer-facing product language, these are **Personalized Apps**.

For the product model and runtime architecture, see the [Micro Apps Guide](https://github.com/The-Wordlab/luzia-nexo/blob/main/docs/guides/micro-apps.md).

Personalized Apps are a first-party structured app runtime inside Nexo. This guide covers the REST API and MCP access for developers who want to create, manage, and query them from the command line or an AI coding assistant.

!!! tip "MCP access"
    All operations on this page are also available as MCP tools.
    Connect an AI coding assistant and build apps through conversation.
    See [MCP Server](mcp.md) for setup.

!!! warning "Dashboard host vs MCP host"
    Use the dashboard hosts (`https://staging.nexo.luzia.com`, `https://nexo.luzia.com`)
    to sign in and create developer keys.

    Use the backend MCP base URL (`https://nexo-cdn-alb.staging.thewordlab.net`,
    `https://luzia-nexo.thewordlab.net`, or `http://localhost:8000`) for MCP connections
    and low-level MCP health checks.

## Authentication

### Developer key (recommended for CLI, MCP, and automation)

Send your developer key in the `X-Api-Key` header:

```bash
curl -H "X-Api-Key: nexo_uak_..." https://nexo.luzia.com/api/micro-apps
```

Get your key from the Nexo dashboard → Profile → Developer Access.
Your developer key identifies you (the person) and works across all Personalized Apps endpoints.

### JWT session (dashboard and browser)

For browser-based access, obtain a user-scoped JWT by posting your email and password to the token endpoint.

### POST /api/auth/token

**JSON body:**

```bash
curl -X POST "https://nexo.luzia.com/api/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}'
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

A form-encoded variant is also available at `POST /api/auth/token/form` for tools that prefer form encoding.

Use the token on all subsequent requests:

```bash
export TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

## List apps

### GET /api/micro-apps

Returns all Personalized Apps owned by the authenticated user.

```bash
curl "https://nexo.luzia.com/api/micro-apps" \
  -H "Authorization: Bearer $TOKEN"
```

**Response** (array of app summaries):

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Shared Expenses",
    "archetype": "shared_expenses",
    "locale": "pt-BR",
    "status": "active",
    "created_at": "2026-04-01T10:00:00Z"
  }
]
```

## Create an app from a prompt

Creating an app is a two-step process: plan a template, then provision.

### Step 1: Plan a template

### POST /api/micro-apps/template-plan

Turn a natural-language prompt into a structured template preview. The response shows what would be created - tables, fields, views, seed data - without actually creating anything.

```bash
curl -X POST "https://nexo.luzia.com/api/micro-apps/template-plan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Help me track my weekly grocery spending",
    "locale": "en"
  }'
```

**Response** (template preview):

```json
{
  "template": {
    "name": "Grocery Spending",
    "archetype": "custom",
    "locale": "en",
    "tables": [
      {
        "key": "expenses",
        "label": "Expenses",
        "fields": [
          { "key": "item", "label": "Item", "type": "text", "required": true },
          { "key": "amount", "label": "Amount", "type": "number", "required": true },
          { "key": "category", "label": "Category", "type": "select", "options": ["produce", "dairy", "meat", "pantry", "other"] },
          { "key": "date", "label": "Date", "type": "date", "required": true }
        ]
      }
    ],
    "views": [
      { "key": "list", "type": "list", "table_key": "expenses" },
      { "key": "summary", "type": "summary", "table_key": "expenses" }
    ],
    "seed_records": [
      { "table_key": "expenses", "values": { "item": "Apples", "amount": 4.50, "category": "produce", "date": "2026-04-10" } }
    ]
  }
}
```

Review the template. If it looks right, provision.

### Step 2: Provision the app

### POST /api/micro-apps/provision-from-template

```bash
curl -X POST "https://nexo.luzia.com/api/micro-apps/provision-from-template" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template": { ... }
  }'
```

Pass the full `template` object from the planning step. The response is the created app with its ID.

## Modify an existing app

Use the operation plan/apply pattern to modify an app's schema or settings.
For guided/stateful apps, that now includes app-level state/schedule/capability
metadata, semantic table/field/view metadata, and record-level workflow metadata.

### POST /api/micro-apps/template-operation-plan

Plan a mutation on an existing app:

```bash
curl -X POST "https://nexo.luzia.com/api/micro-apps/template-operation-plan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "550e8400-e29b-41d4-a716-446655440000",
    "instruction": "Add a store name field to the expenses table"
  }'
```

### POST /api/micro-apps/apply-operation

Execute the planned mutation:

```bash
curl -X POST "https://nexo.luzia.com/api/micro-apps/apply-operation" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "550e8400-e29b-41d4-a716-446655440000",
    "operation": { ... }
  }'
```

## Context endpoint

### GET /api/micro-apps/context.md

Returns a compact markdown summary of all the user's apps, tables, fields, and recent records. Designed for LLM context injection (~300-800 tokens).

```bash
curl "https://nexo.luzia.com/api/micro-apps/context.md" \
  -H "Authorization: Bearer $TOKEN"
```

**Response** (`text/markdown`):

```markdown
## Shared Expenses
Expense tracker | 23 records | Last updated: Apr 10
### expenses (6 fields, 23 records)
Fields: amount (number, required), category (select: food/transport/rent), note (text), spent_at (date, required)
Summary: Total R$1,340.00 | Shared R$480.00
Recent:
- Apr 10: Dinner, R$42.00, food, shared (Maria)
- Apr 9: Uber, R$18.50, transport (João)
```

A JSON variant is available at `GET /api/micro-apps/context`:

```json
{
  "markdown": "## Shared Expenses\n...",
  "app_count": 2,
  "total_records": 45,
  "apps": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Workout Flow",
      "archetype_key": "guided_tracker",
      "playbook_key": "stateful_guided_app",
      "metric_keys": ["completion_ratio", "current_streak"],
      "log_keys": ["activity_log"]
    }
  ]
}
```

For guided, stateful apps, the structured app summaries now expose enough
contract for stateless MCP iteration: archetype/playbook, metric keys, and log
keys. Use `show_app` when the client needs the full app/table/field/view/log
metadata, and `plan_operation` / `apply_operation` when it needs to add or
update fields, views, settings, runtime handoff, or log declarations.

## Surface rendering

### GET /api/micro-apps/{id}/surface

Render a compact card for embedding in chat:

```bash
curl "https://nexo.luzia.com/api/micro-apps/$APP_ID/surface?surface=chat_card" \
  -H "Authorization: Bearer $TOKEN"
```

## MCP access

Nexo's MCP server at `/mcp` exposes Personalized Apps as discoverable tools. Any MCP-compatible client (Claude Code, LangChain, etc.) can discover and call these tools. Auth via your developer key in the `X-Api-Key` header.

### Connect

```bash
# Claude Code example
export NEXO_BASE_URL=http://localhost:8000
claude mcp add --scope project --transport http nexo-server \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: YOUR_DEVELOPER_KEY"
```

Use your **developer key** for MCP. App runtime secrets are for Partner Integration runtime calls, not for MCP.

### Available tools

When connected, `list_tools` returns tools for each active Partner Integration plus Personalized Apps management tools. Tool names are app UUIDs; descriptions include the app's name and capabilities.

### Tool invocation

```json
{
  "name": "<app-uuid>",
  "arguments": {
    "message": "Show me my spending this week",
    "session_id": "cli-session-001"
  }
}
```

For full MCP and A2A protocol details, see [Agent Interop](agent-interop.md).

## Quick reference

The quick reference below covers the AI-assisted workflow. For the full CRUD API (tables, fields, records, views, forms, settings), see the OpenAPI specification at `/docs` on your Nexo instance.

| Operation | Method | Endpoint |
|---|---|---|
| Authenticate | POST | `/api/auth/token` |
| List apps | GET | `/api/micro-apps` |
| Plan template | POST | `/api/micro-apps/template-plan` |
| Provision app | POST | `/api/micro-apps/provision-from-template` |
| Plan mutation | POST | `/api/micro-apps/template-operation-plan` |
| Apply mutation | POST | `/api/micro-apps/apply-operation` |
| Context (markdown) | GET | `/api/micro-apps/context.md` |
| Context (JSON) | GET | `/api/micro-apps/context` |
| Render surface | GET | `/api/micro-apps/{id}/surface` |
| MCP tools | POST | `/mcp` |

## Constraints

- 10 apps per user
- 3 tables per app
- 30 fields per table
- 5,000 records per table
- 6 field types: text, number, boolean, date, select, multi_select
- 4 view types: list, cards, form, summary

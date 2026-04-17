# MCP Server

Nexo exposes an MCP server at `/mcp` (Streamable HTTP). Connect any MCP client to
create and manage Personalized Apps through natural conversation, or invoke Partner
Integration tools programmatically.

## Quick start

Get productive in under 2 minutes:

### 1. Get your developer key

Open the Nexo dashboard → Profile → Developer Access → Create key.
Your key looks like `nexo_uak_...`. This is the only credential you need.

### 2. Set your environment

```bash
export NEXO_DEVELOPER_KEY=nexo_uak_...
export NEXO_BASE_URL=http://localhost:8000
```

Use the MCP backend base URL for your environment:

- local: `http://localhost:8000`
- staging: `https://nexo-cdn-alb.staging.thewordlab.net`
- production: `https://luzia-nexo.thewordlab.net`

The dashboard hosts (`https://staging.nexo.luzia.com`, `https://nexo.luzia.com`) are
where you sign in and create developer keys. Do not use them as the source of truth
for MCP health checks while vanity `/mcp` routing is still being corrected.

### 3. Connect MCP

```bash
claude mcp add --scope project --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"
```

Or run: `bash scripts/connect-mcp.sh`

### 4. Start building

Open Claude Code and say:

> "Create an expense tracker for shared household bills"

The agent calls `plan_app` to generate a template, then `provision_app` to create
the app with tables, fields, views, and seed data.

> "Add a record: $45 dinner, paid by Alice"

> "Add a category field with options: food, transport, housing, utilities"

> "Show me everything I have"

**Recommended workflow:** Always plan before provisioning. Use `show_app` to
verify after provisioning. Use `plan_operation` + `apply_operation` for
incremental changes. Check the result in the dashboard and standalone webview.

If you have the `luzia-nexo` repo checked out, use the `/build-app` slash
command in Claude Code for a guided app creation workflow.

## Authentication

Send your **developer key** in the `X-Api-Key` header. One key, one credential.

Developer keys identify **you** (the person). They are not app-scoped.
Get yours from the Nexo dashboard under Profile → Developer Access.

Your developer key is specific to the Nexo instance where you created it — a staging key does not work on production and vice versa.

Do not confuse with app runtime secrets (`X-App-Secret`) — those are for Partner
Integration webhook auth and are never used with MCP.

For raw `curl` or other low-level HTTP checks, also send:

```bash
-H "Accept: application/json, text/event-stream"
```

That `Accept` header is part of MCP transport negotiation. Without it, a healthy
backend MCP host can return `406 Not Acceptable`.

## Available tools

### Personalized Apps tools

| Tool | Description | Key parameters |
|---|---|---|
| `micro_apps__list_apps` | List all Personalized Apps owned by the authenticated user | -- |
| `micro_apps__create_app` | Create an empty app shell (use when you already know the exact structure) | `name`, `description`, `locale` |
| `micro_apps__show_app` | Get app with full structured contract: app metadata, logs, tables, fields, views, record counts | `app_id` |
| `micro_apps__add_record` | Add a record to a table | `app_id`, `table_key`, `values` |
| `micro_apps__query_app` | Query records with filters and sorting | `app_id`, `table_key`, `filters`, `sort`, `limit` |
| `micro_apps__modify_app` | Update an app's name or description | `app_id`, `name`, `description` |
| `micro_apps__plan_app` | Plan an app from a natural-language prompt (returns template, does not create) | `prompt`, `locale`, `archetype_hint` |
| `micro_apps__provision_app` | Create an app from a template plan (the "make it real" step) | `template` |
| `micro_apps__plan_operation` | Plan a schema or contract change from a prompt (fields, views, settings, runtime handoff, log declarations) | `prompt`, `app_id`, `table_key` |
| `micro_apps__apply_operation` | Execute a planned operation against the database, including structured app/table/field/view/record metadata and log declaration updates | `operation` |
| `micro_apps__get_context` | Get markdown plus structured app summaries, including `metric_keys` and `log_keys`, for stateless iteration across existing apps | -- |

**Two creation paths:**

- **Prompt-driven:** `plan_app` → `provision_app` — describe what you want in natural language, get a complete app with tables, fields, views, and seed data.
- **Manual:** `create_app` → `plan_operation` + `apply_operation` — create an empty shell, then add structure incrementally.

For guided, stateful apps such as workout trackers, the canonical shape can now
include archetype/playbook metadata, schedule config, metric definitions,
semantic field roles, and app log streams. `show_app` and `get_context` expose
that structure so MCP clients can continue editing without hidden assumptions.
The same operation lane also supports private runtime handoff issuance and
revocation when an agent needs to open an interactive app session, and it can
also add or update app log declarations through `plan_operation` /
`apply_operation` without adding another MCP tool.

### Partner Integration tools

Each active Partner Integration is exposed as a tool named by its UUID. The tool description includes the app's name and capabilities. Calling the tool sends a message through the webhook pipeline and returns the response.

## Walkthrough: Create an app from a prompt

This walkthrough shows the exact tool calls an agent makes when you say "Create an expense tracker for a shared apartment."

### 1. Plan the app

The agent calls `micro_apps__plan_app`:

```json
{
  "prompt": "expense tracker for a shared apartment with rent, utilities, and groceries"
}
```

Response:

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
          { "key": "category", "label": "Category", "type": "select", "options": ["rent", "utilities", "groceries", "other"] },
          { "key": "paid_by", "label": "Paid by", "type": "text", "required": true },
          { "key": "date", "label": "Date", "type": "date", "required": true }
        ]
      }
    ],
    "views": [
      { "key": "all_expenses", "type": "list", "table_key": "expenses" },
      { "key": "summary", "type": "summary", "table_key": "expenses" }
    ],
    "seed_records": [
      { "table_key": "expenses", "values": { "description": "April rent", "amount": 1200, "category": "rent", "paid_by": "Alice", "date": "2026-04-01" } }
    ]
  }
}
```

### 2. Provision the app

The agent calls `micro_apps__provision_app` with the template:

```json
{
  "status": "ok",
  "app": { "id": "a1b2c3d4-...", "name": "Shared Apartment Expenses" },
  "tables_created": 1,
  "fields_created": 5,
  "views_created": 2,
  "records_created": 1
}
```

### 3. Inspect the app

The agent calls `micro_apps__show_app` to see the full schema:

```json
{
  "status": "ok",
  "app": {
    "id": "a1b2c3d4-...",
    "name": "Shared Apartment Expenses",
    "tables": [
      {
        "id": "tbl-uuid",
        "key": "expenses",
        "name": "Expenses",
        "record_count": 1,
        "fields": [
          { "key": "description", "label": "Description", "field_type": "text", "is_required": true },
          { "key": "amount", "label": "Amount", "field_type": "number", "is_required": true },
          { "key": "category", "label": "Category", "field_type": "select", "is_required": false },
          { "key": "paid_by", "label": "Paid by", "field_type": "text", "is_required": true },
          { "key": "date", "label": "Date", "field_type": "date", "is_required": true }
        ],
        "views": [
          { "name": "All Expenses", "view_type": "list" },
          { "name": "Summary", "view_type": "summary" }
        ]
      }
    ]
  }
}
```

### 4. Add a record

```json
{
  "status": "ok",
  "record": {
    "id": "rec-uuid",
    "values": { "description": "Groceries", "amount": 85, "category": "groceries", "paid_by": "Bob", "date": "2026-04-12" }
  }
}
```

### 5. Evolve the schema

The agent calls `micro_apps__plan_operation` with `"prompt": "add a settled checkbox"`, then `micro_apps__apply_operation` with the returned operation. A new boolean field appears on the expenses table.

### 6. Get context

The agent calls `micro_apps__get_context` and receives a compact markdown summary of all apps, tables, fields, and recent records — ready for LLM context injection.

## curl examples

### List available tools

```bash
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }'
```

### List your apps

```bash
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__list_apps",
      "arguments": {}
    }
  }'
```

### Plan an app from a prompt

```bash
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__plan_app",
      "arguments": {
        "prompt": "Track my weekly grocery spending",
        "locale": "en"
      }
    }
  }'
```

### Provision an app from a template

```bash
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__provision_app",
      "arguments": {
        "template": { "...template object from plan_app response..." }
      }
    }
  }'
```

### Plan and apply an operation

```bash
# Plan
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__plan_operation",
      "arguments": {
        "prompt": "Add a store name field to the expenses table",
        "app_id": "your-app-uuid"
      }
    }
  }'

# Apply (pass the operation from the plan response)
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 6,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__apply_operation",
      "arguments": {
        "operation": { "...operation object from plan_operation response..." }
      }
    }
  }'
```

### Get context summary

```bash
curl -X POST "${NEXO_BASE_URL}/mcp" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: nexo_uak_your_key_here" \
  -d '{
    "jsonrpc": "2.0",
    "id": 7,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__get_context",
      "arguments": {}
    }
  }'
```

## Connecting other clients

### Claude Code (CLI)

**Option A: Command line (quick, local scope)**

```bash
claude mcp add --scope project --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"
```

Verify:

```bash
claude mcp list          # shows nexo-mcp with status
claude mcp get nexo-mcp  # shows URL and tool count
```

Inside Claude Code, run `/mcp` to see server status and available tools.

To remove: `claude mcp remove nexo-mcp`

**Option B: Project config (shared with team via git)**

Add `.mcp.json` to your repo root:

```json
{
  "mcpServers": {
    "nexo-mcp": {
      "type": "http",
      "url": "${NEXO_BASE_URL}/mcp",
      "headers": {
        "X-Api-Key": "${NEXO_DEVELOPER_KEY}"
      }
    }
  }
}
```

Team members who clone the repo get the MCP connection automatically. Each developer sets both `NEXO_DEVELOPER_KEY` and `NEXO_BASE_URL` in their shell.

**Option C: User config (all projects, private)**

```bash
claude mcp add --scope user --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"
```

### Claude Desktop (macOS / Windows)

Edit the config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nexo-mcp": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "X-Api-Key": "nexo_uak_your_key_here"
      }
    }
  }
}
```

Restart Claude Desktop after editing. The Nexo tools appear in the tool picker.

Note: Claude Desktop does not support `${VAR}` env var expansion — use the literal key value.

### Cursor

1. Open Settings → MCP
2. Click "Add MCP Server"
3. Set:
    - Name: `nexo-mcp`
    - Transport: HTTP
    - URL: `${NEXO_BASE_URL}/mcp`
    - Headers: `X-Api-Key: nexo_uak_your_key_here`

No restart needed — Cursor picks up the change immediately.

### Windsurf

1. Open Settings → search "MCP"
2. Click "Manage plugins" under Plugins (MCP Servers)
3. Add server with the same URL and headers as above

### Any MCP client (generic)

The Nexo MCP server is a standard Streamable HTTP endpoint. Any client that supports MCP can connect with:

- **URL:** `${NEXO_BASE_URL}/mcp`
- **Transport:** Streamable HTTP (JSON-RPC over HTTP POST)
- **Auth:** `X-Api-Key: nexo_uak_...` header on every request
- **No session required** — each request is independently authenticated

### Switching environments

```bash
# Hosted environment
export NEXO_BASE_URL=https://your-nexo-mcp-base-url

# Verified staging backend host
export NEXO_BASE_URL=https://nexo-cdn-alb.staging.thewordlab.net

# Verified production backend host
export NEXO_BASE_URL=https://luzia-nexo.thewordlab.net

# Local development
export NEXO_BASE_URL=http://localhost:8000
```

Developer keys are per-environment — a key created on staging does not work on production. The dashboard host and MCP host can differ during rollout, so always use the MCP base URL for your environment.

## Debugging with MCP Inspector

The MCP Inspector is a browser-based tool for exploring and testing MCP servers interactively:

```bash
npx @modelcontextprotocol/inspector http "${NEXO_BASE_URL}/mcp"
```

Add your developer key in the Inspector's headers configuration panel (`X-Api-Key: nexo_uak_...`). This is useful for testing tool schemas and responses without an AI assistant.

## Related docs

- [Personalized Apps API](micro-apps-api.md) -- same operations via REST
- [Tutorial: Create an app from the terminal](tutorial-create-app-from-terminal.md) -- full walkthrough
- [Agent Interop](agent-interop.md) -- MCP and A2A protocol details

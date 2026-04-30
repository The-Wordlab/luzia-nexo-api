# Luzia Nexo API

Build apps that run inside Luzia.

Nexo is the apps runtime behind Luzia. You bring the domain logic -
Nexo handles delivery, threading, streaming, identity, and rich UI.

The important builder model is black-box:

- you do not need to understand Nexo internals
- you interact through the dashboard, REST API, MCP, and runtime URLs
- a Nexo-backed app can become a Luzia capability with durable state and UI

## One app model

Every Nexo app can combine:

- **Structured data** - tables, records, Knowledge Packs, and derived
  projections managed by Nexo
- **A webhook** (optional) - your backend handles chat messages and events
  with signed webhook delivery (HMAC-SHA256), sync JSON or streaming SSE
  responses, rich cards, actions, and prompt suggestions

Apps without a webhook are fully managed by Nexo. Apps with a webhook get
the same structured data features plus your custom backend logic.

Apps published in Nexo are automatically discoverable by Luzia at runtime -
no hardcoded skill catalog needed.

[Webhook quickstart](quickstart.md){ .md-button .md-button--primary }
[Structured apps API](micro-apps-api.md){ .md-button }
[MCP Server](mcp.md){ .md-button }

## Quick start

**App with a webhook** - implement one endpoint:

```bash
# 1. Clone a starter
git clone https://github.com/The-Wordlab/luzia-nexo-api
cd examples/webhook/minimal/python

# 2. Run locally
pip install -r requirements.txt && python server.py

# 3. Point Nexo at your endpoint
# Dashboard > Apps > Your App > Webhook > set URL + signing secret
```

**App without a webhook** - create from the command line:

```bash
# 1. Get a developer key from Dashboard > Profile > Developer Access
export NEXO_DEVELOPER_KEY=nexo_uak_...
export NEXO_BASE_URL=https://nexo-cdn-alb.staging.thewordlab.net

# 2. Connect MCP
claude mcp add --scope project --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"

# 3. Ask your assistant:
#    "Create an expense tracker for shared household bills"
```

You do not need to know how the Nexo runtime is implemented internally. Treat
it as the app backend and interact with it through the dashboard, REST API,
and MCP tools.

Recommended creation grammar:

1. clarify
2. `plan_app`
3. review
4. `provision_app`
5. inspect with `show_app` or `get_context`
6. evolve with `plan_operation` / `apply_operation`

If the app shape is already known up front, use the one-call REST provision
endpoint instead of forcing the schema through prompt discovery.

This is also how to read Nexo strategically as a builder:

- build the app/backend once
- expose capability through API or MCP
- open the runtime/UI when needed
- let Luzia consume the same app as a durable capability rather than as a
  one-off tool call

## Browse examples

See working Connected Apps you can clone, customize, and deploy:

[Demo Catalog](demos.md){ .md-button }

## Docs

| Topic | Description |
|---|---|
| [Webhook Quickstart](quickstart.md) | Get a webhook app live in minutes |
| [Structured Apps API](micro-apps-api.md) | REST API for app creation and management |
| [Knowledge Packs](knowledge-packs.md) | App-attached reference data |
| [MCP Server](mcp.md) | AI coding assistant integration |
| [Partner API Reference](partner-api-reference.md) | Full webhook and runtime contract |
| [Capability Discovery](capability-discovery.md) | Dynamic app and skill discovery via the manifest endpoint |
| [Developer Auth](developer-auth.md) | Developer keys, MCP auth, REST API auth |
| [External App Auth Bridge (Planned)](auth-bridge-handoff.md) | Planned Nexo-owned login and one-time callback model for externally hosted apps |
| [Demo Catalog](demos.md) | Browse and deploy example apps |
| [Hosting](hosting.md) | Deploy to Cloud Run |

!!! tip "Nexo Dashboard"
    Manage apps, signing secrets, and live tests at
    [nexo.luzia.com](https://nexo.luzia.com).

## Terminology

- **App** - the unified Nexo app model. Can have structured data, a
  webhook, or both.
- **Webhook** - optional. When set, Nexo dispatches chat messages and
  events to your backend with HMAC-signed requests.
- **Structured data** - tables, records, Knowledge Packs managed by Nexo.
- In code, you may see the technical term **micro_apps** for the underlying
  model.

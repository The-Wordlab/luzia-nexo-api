# Luzia Nexo API

Build apps that run inside Luzia.

Nexo is the apps runtime behind Luzia. You bring the domain logic -
Nexo handles delivery, threading, streaming, identity, and rich UI.

The important builder model is black-box:

- you do not need to understand Nexo internals
- you interact through the dashboard, REST API, MCP, and runtime URLs
- a Nexo-backed app can become a Luzia capability with durable state and UI

## Two ways to build

### Connected Apps

Your backend receives webhook requests with conversation context and returns
responses. You own the infrastructure and the domain logic.

- Signed webhook delivery (HMAC-SHA256)
- Sync JSON or streaming SSE responses
- Rich cards, actions, and prompt suggestions
- Proactive push events to subscriber threads

[Get started with Connected Apps](quickstart.md){ .md-button .md-button--primary }

### Personalized Apps

Structured apps you create and manage through Nexo APIs or MCP. Nexo owns the
storage, rendering, and runtime - you define the shape.

- Create apps with tables, fields, and Knowledge Packs
- Use MCP from Claude Code, Codex, or any AI coding assistant
- Use one-call provisioning when you already know the exact schema
- Attach reference data through Knowledge Packs
- Publish to web or native via domain-verified sessions and launch contracts

[Personalized Apps API](micro-apps-api.md){ .md-button }
[MCP Server](mcp.md){ .md-button }

## Quick start

**Connected App** - implement one webhook endpoint:

```bash
# 1. Clone a starter
git clone https://github.com/The-Wordlab/luzia-nexo-api
cd examples/webhook/minimal/python

# 2. Run locally
pip install -r requirements.txt && python server.py

# 3. Point Nexo at your endpoint
# Dashboard > Apps > Your App > Webhooks > set URL + secret
```

**Personalized App** - create from the command line:

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
| [Quickstart](quickstart.md) | Get a Connected App live in minutes |
| [Personalized Apps API](micro-apps-api.md) | REST API for structured apps |
| [Knowledge Packs](knowledge-packs.md) | App-attached reference data |
| [MCP Server](mcp.md) | AI coding assistant integration |
| [Partner API Reference](partner-api-reference.md) | Full webhook and runtime contract |
| [Capability Discovery](capability-discovery.md) | Dynamic app and skill discovery via the manifest endpoint |
| [Developer Auth](developer-auth.md) | Developer keys, MCP auth, REST API auth |
| [External App Auth Bridge (Planned)](auth-bridge-handoff.md) | Planned Nexo-owned login and one-time callback model for externally hosted apps |
| [Demo Catalog](demos.md) | Browse and deploy example apps |
| [Hosting](hosting.md) | Deploy to Cloud Run |

!!! tip "Nexo Dashboard"
    Manage apps, webhook secrets, and live tests at
    [nexo.luzia.com](https://nexo.luzia.com).

## Product language

- **Personalized Apps** is the product name for structured apps in Nexo.
- **Connected Apps** is the product name for webhook-backed partner apps.
- In code, you may see the technical term **micro apps** for Personalized Apps.

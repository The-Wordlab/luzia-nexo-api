# Luzia Nexo API

Build apps that run inside Luzia.

Nexo is the apps runtime behind Luzia. You bring the domain logic -
Nexo handles delivery, threading, streaming, identity, and rich UI.

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
- Attach reference data through Knowledge Packs
- Publish to web or native via domain-verified sessions

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

# 2. Connect MCP
claude mcp add nexo-mcp "https://nexo-cdn-alb.staging.thewordlab.net/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"

# 3. Ask your assistant to create an app
```

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
| [Developer Auth](developer-auth.md) | Developer keys, MCP auth, REST API auth |
| [Demo Catalog](demos.md) | Browse and deploy example apps |
| [Hosting](hosting.md) | Deploy to Cloud Run |

!!! tip "Nexo Dashboard"
    Manage apps, webhook secrets, and live tests at
    [nexo.luzia.com](https://nexo.luzia.com).

## Product language

- **Personalized Apps** is the product name for structured apps in Nexo.
- **Connected Apps** is the product name for webhook-backed partner apps.
- In code, you may see the technical term **micro apps** for Personalized Apps.

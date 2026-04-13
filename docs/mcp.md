# MCP Server

Nexo exposes an MCP (Model Context Protocol) server at `/mcp` that lets AI coding assistants discover and call Nexo tools over Streamable HTTP. When enabled, the server publishes two categories of tools:

- **Webhook app tools** -- one tool per active webhook app, letting an MCP client send messages through the same pipeline that powers the chat UI.
- **Micro Apps tools** -- CRUD operations for creating, querying, and managing structured Micro Apps.

## Connecting from Claude Code

```bash
claude mcp add --transport http nexo-mcp http://localhost:8001/mcp
```

For a remote Nexo instance:

```bash
claude mcp add --transport http nexo-mcp https://nexo.luzia.com/mcp
```

Claude Code will prompt for the API key on first use, or you can set it in your MCP config file.

## Authentication

Every request must include an `X-Api-Key` header. The key is matched against app webhook secrets using bcrypt, so you can reuse an existing app's `webhook_secret` as your MCP API key.

Enable the server and set a key in your environment:

```bash
MCP_SERVER_ENABLED=true
MCP_SERVER_API_KEY=your-secret-key
```

## Available tools

### Webhook app tools

Each active webhook app is exposed as a tool named by its UUID. The tool description includes the app's name and capabilities. Calling the tool sends a message through the webhook pipeline and returns the response.

### Micro Apps tools

| Tool | Description |
|---|---|
| `micro_apps__list_apps` | List all Micro Apps owned by the authenticated user |
| `micro_apps__create_app` | Create a new Micro App from a natural-language prompt |
| `micro_apps__show_app` | Show an app's schema, records, and surface card |
| `micro_apps__add_record` | Add a record to an app's table |
| `micro_apps__query_app` | Answer a question using an app's structured data |
| `micro_apps__modify_app` | Modify an app's schema or settings |

## curl examples

### List available tools

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-secret-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }'
```

### Call a tool

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-secret-key" \
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

### Create an app via MCP

```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-secret-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "micro_apps__create_app",
      "arguments": {
        "prompt": "Track my weekly grocery spending",
        "locale": "en"
      }
    }
  }'
```

## Debugging with MCP Inspector

The MCP Inspector is a browser-based tool for exploring and testing MCP servers interactively:

```bash
npx @modelcontextprotocol/inspector http http://localhost:8001/mcp
```

This opens a UI where you can browse available tools, call them with custom arguments, and inspect the JSON-RPC responses. Add your API key in the Inspector's headers configuration panel.

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `MCP_SERVER_ENABLED` | `false` | Enable the MCP endpoint at `/mcp` |
| `MCP_SERVER_API_KEY` | -- | Required when enabled. Authenticates MCP clients. |

## Related docs

- [Micro Apps API](micro-apps-api.md) -- REST API for Micro Apps (same operations, HTTP interface)
- [Agent Interop](agent-interop.md) -- full MCP and A2A protocol details

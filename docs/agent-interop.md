# Agent Interoperability (MCP & A2A)

Nexo is fully compatible with the two dominant open agent protocols: **Model Context Protocol (MCP)** and **Google's Agent-to-Agent (A2A) protocol**. This means any LLM orchestrator or AI agent that speaks either protocol can discover Nexo's capabilities and delegate tasks to them — without custom integration code.

Both integrations are **feature-gated** and disabled by default. Enable them on your deployment using the environment variables described in [Configuration](#configuration).

---

## MCP Server

**When to use:** You are building an LLM agent or orchestrator (e.g., LangChain, LangGraph, Claude) and want Nexo's capabilities available as callable tools alongside your own tools.

Nexo implements the [Model Context Protocol](https://modelcontextprotocol.io/) Streamable HTTP transport at `/mcp`. Every active Partner Integration registered in Nexo automatically appears as a discoverable MCP tool, and Personalized Apps management tools are exposed alongside it. The tool name is the app's UUID; its description comes from the app's name, description, and declared capabilities.

### Endpoint

```
POST https://nexo.luzia.com/mcp
```

This single endpoint handles all MCP protocol traffic — tool listing and tool invocation — using Streamable HTTP transport.

### Authentication

Pass your **developer key** in the `X-Api-Key` header on every request:

```
X-Api-Key: <developer_key>
```

Your developer key is the only credential needed. Get it from the Nexo dashboard under Profile.

### Tool schema

Each tool exposes a consistent input schema:

```json
{
  "name": "<app-uuid>",
  "description": "App description | Capabilities: ...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "description": "The user message to send to this skill"
      },
      "session_id": {
        "type": "string",
        "description": "An opaque session identifier to correlate multi-turn conversations"
      }
    },
    "required": ["message"]
  }
}
```

Providing a stable `session_id` across calls lets Nexo maintain conversation context within a thread. If omitted, each call is treated as a fresh turn.

Tool results are returned as structured JSON text containing the assistant reply, any source attribution, and a `pending` flag for async capabilities.

### Connecting from LangChain / LangGraph

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient(
    {
        "nexo": {
            "transport": "streamable_http",
            "url": "https://nexo.luzia.com/mcp",
            "headers": {"X-Api-Key": "<developer_key>"},
        }
    }
)

tools = await client.get_tools()
# Returns one tool per active Nexo app
# e.g. nexo_food_ordering, nexo_news_search, nexo_sports_live
```

You can then pass `tools` directly to any LangGraph agent:

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=your_llm,
    tools=[*your_local_tools, *tools],
)
```

### Listing tools via curl

```bash
# Discover available tools
curl -X POST "https://nexo.luzia.com/mcp" \
  -H "X-Api-Key: YOUR_DEVELOPER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Calling a tool via curl

```bash
# Call a tool by its app UUID
curl -X POST "https://nexo.luzia.com/mcp" \
  -H "X-Api-Key: YOUR_DEVELOPER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "YOUR_APP_UUID",
      "arguments": {
        "message": "What are the top news stories today?",
        "session_id": "my-session-abc123"
      }
    }
  }'
```

---

## A2A Protocol

**When to use:** You are building an AI agent that needs to delegate tasks to another agent, maintain multi-turn conversation state across systems, or discover what Nexo is capable of without prior knowledge.

Nexo implements [Google's Agent-to-Agent (A2A) protocol](https://google.github.io/A2A/). This enables agent-to-agent discovery and task delegation: an external agent can query Nexo's capabilities, then delegate tasks to specific skills. Nexo routes each task to the appropriate webhook-backed app and returns a structured A2A task response.

### Agent card (public discovery)

```
GET https://nexo.luzia.com/.well-known/agent.json
```

This endpoint is public — no authentication required. It returns an aggregate agent card listing all active skills currently hosted on Nexo. The card is refreshed automatically as apps are approved or deactivated (with a short cache for performance).

```bash
curl "https://nexo.luzia.com/.well-known/agent.json"
```

Example response:

```json
{
  "name": "Luzia Nexo",
  "description": "AI partner orchestration platform",
  "url": "https://nexo.luzia.com",
  "version": "1.0",
  "authentication": {
    "schemes": ["apiKey"]
  },
  "skills": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "News Research",
      "description": "Real-time news search and summarization with source attribution",
      "inputModes": ["text"],
      "outputModes": ["text", "data"],
      "metadata": { "nexo_app_id": "550e8400-e29b-41d4-a716-446655440000" }
    },
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "name": "Live Sports",
      "description": "Live match scores, standings, and sports news",
      "inputModes": ["text"],
      "outputModes": ["text", "data"],
      "metadata": { "nexo_app_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7" }
    }
  ]
}
```

Use the `id` values from the skills array as `skill_id` when sending messages.

### Authentication (send/stream/poll)

All message and task endpoints require an API key:

```
X-Api-Key: <a2a_api_key>
```

### Task lifecycle

A2A tasks move through the following states:

| Status | Meaning |
|---|---|
| `submitted` | Task has been received and queued |
| `working` | Task has been accepted and is being processed |
| `completed` | Task finished successfully |
| `failed` | Task encountered an error |
| `input-required` | Task is paused waiting for user input (reserved for future use) |

### POST /a2a/message/send

Synchronous single-turn request. Nexo routes the message to the skill identified by `metadata.skill_id`, waits for the webhook response, and returns a completed (or failed) task.

**Request body:**

```json
{
  "message": {
    "role": "user",
    "parts": [
      { "type": "text", "text": "What are today's top stories?" }
    ]
  },
  "metadata": {
    "skill_id": "550e8400-e29b-41d4-a716-446655440000",
    "session_id": "optional-session-id-for-multi-turn"
  }
}
```

| Field | Required | Description |
|---|---|---|
| `message.role` | yes | Must be `"user"` |
| `message.parts` | yes | Array of parts. At least one must be `{"type":"text","text":"..."}` |
| `metadata.skill_id` | yes | UUID of the Nexo app to route to (from the agent card) |
| `metadata.session_id` | no | Stable identifier to correlate multi-turn exchanges |

**Response:**

```json
{
  "task": {
    "id": "a4f1c2d3-...",
    "status": "completed",
    "messages": [
      {
        "role": "agent",
        "parts": [
          { "type": "text", "text": "Here are today's top stories..." }
        ]
      }
    ],
    "artifacts": []
  }
}
```

**curl example:**

```bash
curl -X POST "https://nexo.luzia.com/a2a/message/send" \
  -H "X-Api-Key: YOUR_A2A_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "What are today'\''s top stories?"}]
    },
    "metadata": {
      "skill_id": "YOUR_SKILL_ID"
    }
  }'
```

### POST /a2a/message/stream

Streaming variant using Server-Sent Events (SSE). The connection emits `task_update` events as the task progresses from `working` to `completed`.

Same request body as `/a2a/message/send`.

**SSE event stream:**

```
event: task_update
data: {"id":"a4f1c2d3-...","status":"working","messages":[],"artifacts":[]}

event: task_update
data: {"id":"a4f1c2d3-...","status":"completed","messages":[{"role":"agent","parts":[{"type":"text","text":"Here are today'\''s top stories..."}]}],"artifacts":[]}
```

**curl example:**

```bash
curl -X POST "https://nexo.luzia.com/a2a/message/stream" \
  -H "X-Api-Key: YOUR_A2A_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Who won last night'\''s match?"}]
    },
    "metadata": {
      "skill_id": "YOUR_SKILL_ID",
      "session_id": "user-session-xyz"
    }
  }'
```

### GET /a2a/tasks/{task_id}

Poll a previously submitted task by its ID. Useful if you issued a send and want to check status asynchronously, or if you want to retrieve a completed task after the fact.

Tasks are retained for 5 minutes after creation. After that window, a 404 is returned.

**curl example:**

```bash
curl "https://nexo.luzia.com/a2a/tasks/a4f1c2d3-1234-5678-abcd-ef0123456789" \
  -H "X-Api-Key: YOUR_A2A_API_KEY"
```

**Response** (same `A2ATask` shape as send/stream):

```json
{
  "id": "a4f1c2d3-1234-5678-abcd-ef0123456789",
  "status": "completed",
  "messages": [...],
  "artifacts": []
}
```

### Multi-turn conversations

Pass a consistent `session_id` in `metadata` across requests to the same skill. Nexo correlates requests to a single conversation thread, preserving context across turns:

```bash
# Turn 1
curl -X POST "https://nexo.luzia.com/a2a/message/send" \
  -H "X-Api-Key: YOUR_A2A_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {"role":"user","parts":[{"type":"text","text":"Plan a 3-day trip to Lisbon"}]},
    "metadata": {"skill_id": "YOUR_SKILL_ID", "session_id": "trip-planner-001"}
  }'

# Turn 2 — Nexo remembers the previous turn
curl -X POST "https://nexo.luzia.com/a2a/message/send" \
  -H "X-Api-Key: YOUR_A2A_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {"role":"user","parts":[{"type":"text","text":"Add a day trip to Sintra"}]},
    "metadata": {"skill_id": "YOUR_SKILL_ID", "session_id": "trip-planner-001"}
  }'
```

---

## Configuration

MCP is always enabled. A2A is opt-in:

| Variable | Default | Description |
|---|---|---|
| `A2A_SERVER_ENABLED` | `false` | Set to `true` to enable A2A endpoints at `/a2a/*` |
| `A2A_SERVER_API_KEY` | `""` | API key required in `X-Api-Key` header for A2A message/task endpoints |

The agent card at `/.well-known/agent.json` is always public once `A2A_SERVER_ENABLED=true`, regardless of the API key setting. Discovery must be unauthenticated per the A2A specification.

### Example: enabling A2A on a Cloud Run deployment

```bash
gcloud run services update nexo-backend \
  --set-env-vars A2A_SERVER_ENABLED=true,A2A_SERVER_API_KEY=your-a2a-key
```

---

## Choosing between MCP and A2A

| | MCP | A2A |
|---|---|---|
| **Best for** | LLM tool invocation — the model decides which tool to call | Agent delegation — one agent hands off a task to another |
| **Discovery** | Tool listing via MCP protocol | Public agent card at `/.well-known/agent.json` |
| **Session state** | Optional `session_id` parameter | Optional `session_id` in metadata |
| **Streaming** | Streamable HTTP transport | SSE (`/a2a/message/stream`) |
| **Rich output** | Structured JSON result | Task with messages and artifacts |
| **Frameworks** | LangChain, LangGraph, Claude, any MCP client | Any A2A client, LangGraph Agent Server |

Both protocols route through the same underlying capability layer, so the response content is equivalent — choose based on your orchestration framework's preferences.

---

## References

- [Model Context Protocol specification](https://modelcontextprotocol.io/)
- [Google Agent-to-Agent (A2A) specification](https://google.github.io/A2A/)
- [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) — MCP client for LangChain and LangGraph
- [Nexo Partner API Reference](partner-api-reference.md) — webhook integration and push events

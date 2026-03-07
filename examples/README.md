# Examples

Runnable Nexo integration examples.

## Docker Compose quickstart

Run all webhook examples with one command:

```bash
cd examples/
cp .env.example .env      # fill in API keys as needed
docker compose up --build
```

### Port reference

| Service     | Host port | Endpoint        | Description                              |
|-------------|-----------|-----------------|------------------------------------------|
| minimal     | 8080      | POST /webhook   | Echo server, minimal webhook contract    |
| structured  | 8081      | POST /          | Locale-aware greetings, card hints       |
| advanced    | 8082      | POST /          | Connector actions, idempotency, retry    |
| news-rag    | 8090      | POST /          | RSS news RAG via ChromaDB + LLM          |
| sports-rag  | 8091      | POST /          | Sports RSS + match data RAG              |
| travel-rag  | 8092      | POST /          | Travel destination + blog RAG            |

### Quick smoke test

```bash
# minimal
curl -s -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"message": {"content": "hello"}}' | jq .

# news-rag health
curl -s http://localhost:8090/health | jq .
```

### LLM configuration

The RAG examples default to `ollama/llama3.2`. Install [Ollama](https://ollama.ai/) locally
and run `ollama pull llama3.2` before starting, or set `LLM_MODEL=gpt-4o` and
`OPENAI_API_KEY=sk-...` in `.env` to use OpenAI.

### Pointing Nexo at local services

Set webhook URLs in the Nexo dashboard to `http://host.docker.internal:<port>/<path>`
(or your machine's LAN IP if Nexo runs in Docker on the same host).

### Stopping

```bash
docker compose down       # stop containers, keep volumes
docker compose down -v    # stop containers and delete ChromaDB volumes
```

Includes an explicit **OpenClaw Bridge** example at `webhook/openclaw-bridge` for teams that want a webhook adapter between Nexo payloads and OpenClaw `/v1/responses`.

Profile context note:
- Webhook payloads include consented profile context (for example `locale`, `language`, `location`, `age`, `date_of_birth`, `gender`, `dietary_preferences`, and preferences/facts).
- Additional attributes are added over time while keeping backward compatibility.
- Build examples and integrations to safely ignore unknown fields.

Folders:
- `webhook/minimal`
- `webhook/openclaw-bridge`
- `webhook/structured`
- `webhook/advanced`
- `webhook/news-rag`
- `webhook/sports-rag`
- `webhook/travel-rag`
- `partner-api/proactive`
- `hosted/python`
- `hosted/typescript`
- `hosted/demo-receiver`

Run all example tests from the repo root:

```bash
make test-examples
```

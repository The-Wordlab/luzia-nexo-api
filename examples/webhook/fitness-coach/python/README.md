# Fitness Coach Webhook

Webhook-backed fitness coaching example for Nexo.

## Intents

| Intent | Prompt examples | Output |
|---|---|---|
| `workout_plan` | "Design a 4-week beginner workout plan" | Weekly plan card + actions |
| `progress_check` | "I ran 5km in 28 minutes, how am I doing?" | Progress snapshot card + targets |
| `nutrition_guidance` | "What should I eat before a morning workout?" | Nutrition guidance card |

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8097
```

Vertex ADC default (production style):

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<project>
export GOOGLE_CLOUD_LOCATION=europe-west1
```

Optional OpenAI override for development:

```bash
export OPENAI_API_KEY=sk-...
export LLM_MODEL=openai/gpt-4o-mini
```

## Endpoints

- `GET /` service info
- `GET /health` health check
- `POST /` main webhook endpoint (JSON or SSE)

## Environment variables

| Variable | Default |
|---|---|
| `WEBHOOK_SECRET` | `""` |
| `LLM_MODEL` | `vertex_ai/gemini-2.5-flash` |
| `STREAMING_ENABLED` | `true` |

# Language Tutor Webhook

Webhook-backed language tutoring example for Nexo.

## Intents

| Intent | Prompt examples | Output |
|---|---|---|
| `phrase_help` | "Teach me how to order food in Italian" | Phrase card |
| `quiz` | "Give me a quick Spanish conversation quiz" | Quiz card |
| `lesson_plan` | "Create a beginner plan in Portuguese" | 4-week lesson plan card |

Run locally:

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8099
```

# LLM-Powered Webhook Base

Reusable base classes for building LLM-powered Nexo webhook examples.

## What's inside

```
base/
  __init__.py      -- public exports
  app.py           -- BaseWebhookApp (FastAPI scaffold, HMAC verification, profile extraction)
  contract.py      -- WebhookRequest / WebhookResponse Pydantic models
  llm.py           -- AssistantChain, AssistantGraph, create_llm() (litellm wrapper)
  prompts.py       -- Canned system prompts (e-commerce, fitness coach)

assistant_ecommerce.py  -- Example: e-commerce support assistant using LangChain
```

## Usage

Subclass `BaseWebhookApp` and implement two methods:

```python
from base import BaseWebhookApp, WebhookRequest, WebhookResponse, build_text_response

class MyAssistant(BaseWebhookApp):
    def get_system_prompt(self) -> str:
        return "You are a helpful assistant."

    async def handle_message(self, request: WebhookRequest) -> WebhookResponse:
        return build_text_response(f"Hello, {request.message.content}!")

app = MyAssistant().create_app()
```

Or use the factory function for simpler cases:

```python
from base import create_app, WebhookRequest, WebhookResponse, build_text_response

async def handle(request: WebhookRequest) -> WebhookResponse:
    return build_text_response("Hello!")

app = create_app("You are a helpful assistant.", handle)
```

## Running the e-commerce example

```bash
cd examples/webhook/llm-powered
pip install -r requirements.txt
OPENAI_API_KEY=sk-... python assistant_ecommerce.py
```

## Tests

```bash
pytest test_llm_base.py test_contract_compat.py -v
```

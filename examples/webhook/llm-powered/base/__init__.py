"""LLM-powered webhook base modules."""

from base.contract import (
    WebhookRequest,
    WebhookResponse,
    WebhookProfile,
    WebhookMessage,
    WebhookContext,
    build_text_response,
    build_response_with_suggestions,
)
from base.llm import (
    AssistantChain,
    AssistantGraph,
    create_llm,
    LLMConfig,
)
from base.app import BaseWebhookApp, create_app, WebhookConfig
from base.prompts import (
    get_prompt_for_scenario,
    ECOMMERCE_ASSISTANT_PROMPT,
    FITNESS_COACH_PROMPT,
)

__all__ = [
    "WebhookRequest",
    "WebhookResponse", 
    "WebhookProfile",
    "WebhookMessage",
    "WebhookContext",
    "build_text_response",
    "build_response_with_suggestions",
    "AssistantChain",
    "AssistantGraph",
    "create_llm",
    "LLMConfig",
    "BaseWebhookApp",
    "create_app",
    "WebhookConfig",
    "get_prompt_for_scenario",
    "ECOMMERCE_ASSISTANT_PROMPT",
    "FITNESS_COACH_PROMPT",
]

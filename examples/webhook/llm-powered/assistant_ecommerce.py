#!/usr/bin/env python3
"""
E-commerce Assistant - LLM-powered webhook example.

This example demonstrates:
1. Using LangChain for AI-powered responses
2. Profile-aware personalization
3. Context-aware suggestions
4. Conversation history handling

Run with:
    pip install -r requirements.txt
    python assistant_ecommerce.py

Set OPENAI_API_KEY or LITELLM_API_KEY to use the LLM.
"""

import os
import logging
from typing import Any

from base import (
    BaseWebhookApp,
    WebhookConfig,
    WebhookRequest,
    WebhookResponse,
    build_response_with_suggestions,
    create_llm,
    LLMConfig,
)
from base.prompts import ECOMMERCE_ASSISTANT_PROMPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PROMPT_SUGGESTIONS = [
    "Track my order",
    "Browse menu",
    "Contact support",
]


class EcommerceAssistant(BaseWebhookApp):
    """E-commerce customer support assistant using LangChain."""
    
    def __init__(self, config: WebhookConfig | None = None):
        super().__init__(config)
        self.llm = create_llm(LLMConfig(
            model=self.config.model,
            temperature=self.config.temperature,
        ))
        self._chain = None
    
    @property
    def chain(self):
        """Lazy-load the LangChain."""
        if self._chain is None:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.messages import MessagesPlaceholder
            from langchain_openai import ChatOpenAI
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", ECOMMERCE_ASSISTANT_PROMPT),
                MessagesPlaceholder(variable_name="history", optional=True),
                ("human", "{message}"),
            ])
            
            self._chain = prompt | self.llm
        
        return self._chain
    
    def get_system_prompt(self) -> str:
        return ECOMMERCE_ASSISTANT_PROMPT
    
    async def handle_message(self, request: WebhookRequest) -> WebhookResponse:
        """Handle incoming message with LLM."""
        user_message = request.message.content or ""
        
        if not user_message:
            name = request.profile.name if request.profile else None
            greeting = f"Hi{name}! How can I help you today?" if name else "Hi! How can I help you today?"
            return build_response_with_suggestions(
                greeting,
                DEFAULT_PROMPT_SUGGESTIONS,
            )
        
        profile_context = self._get_profile_context(request.profile)
        
        history = self._build_history(request)
        
        try:
            response = self.chain.invoke({
                "message": user_message,
                "history": history,
                "name": request.profile.name if request.profile else None,
            })
            
            text = response.content
            
            suggestions = self._get_suggestions(user_message, request.context)
            if suggestions:
                return build_response_with_suggestions(text, suggestions)
            else:
                return build_response_with_suggestions(text, DEFAULT_PROMPT_SUGGESTIONS)
                
        except Exception as e:
            logger.exception(f"LLM error: {e}")
            return build_response_with_suggestions(
                "I apologize, but I'm having trouble processing your request right now. "
                "Please try again or contact support if this continues.",
                DEFAULT_PROMPT_SUGGESTIONS,
            )
    
    def _build_history(self, request: WebhookRequest) -> list[dict[str, str]]:
        """Build conversation history from webhook request."""
        if not request.history_tail:
            return []
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in request.history_tail[-5:]
        ]
    
    def _get_suggestions(self, message: str, context) -> list[str] | None:
        """Get contextual suggestions based on user message."""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["order", "track", "status", "delivery"]):
            return ["Check order status", "Modify order", "Cancel order"]
        
        if any(word in message_lower for word in ["menu", "food", "eat", "restaurant"]):
            return ["Browse categories", "Search for items", "View deals"]
        
        if any(word in message_lower for word in ["help", "support", "problem", "issue"]):
            return ["Talk to agent", "FAQ", "Call support"]
        
        return None


app = EcommerceAssistant().create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

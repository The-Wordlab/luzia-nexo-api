"""Base FastAPI webhook application.

Provides a reusable foundation for LLM-powered webhook examples.
"""

import hashlib
import hmac
import os
import logging
from abc import ABC, abstractmethod
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from base.contract import (
    WebhookRequest,
    WebhookResponse,
    WebhookProfile,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebhookConfig(BaseModel):
    """Configuration for the webhook server."""
    webhook_secret: str | None = None
    system_prompt: str | None = None
    model: str = "vertex_ai/gemini-2.5-flash"
    temperature: float = 0.7


class BaseWebhookApp(ABC):
    """Abstract base class for webhook applications.
    
    Subclass this to create your own LLM-powered webhook.
    
    Example:
        class MyAssistant(BaseWebhookApp):
            def get_system_prompt(self) -> str:
                return "You are a helpful assistant..."
            
            async def handle_message(self, request: WebhookRequest) -> WebhookResponse:
                # Your logic here
                return build_text_response("Hello!")
        
        app = MyAssistant().create_app()
    """
    
    def __init__(self, config: WebhookConfig | None = None):
        self.config = config or WebhookConfig()
        self._app: FastAPI | None = None
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for the LLM.
        
        Override this in your subclass to define the assistant's personality.
        """
        raise NotImplementedError
    
    @abstractmethod
    async def handle_message(self, request: WebhookRequest) -> WebhookResponse:
        """Handle an incoming webhook message.
        
        Override this to implement your assistant's logic.
        
        Args:
            request: The parsed webhook request containing message, profile, context
            
        Returns:
            WebhookResponse to send back to Nexo
        """
        raise NotImplementedError
    
    def _verify_signature(self, request: Request, body: bytes) -> None:
        """Verify HMAC signature if configured."""
        secret = self.config.webhook_secret or os.environ.get("WEBHOOK_SECRET", "")
        if not secret:
            return
        
        provided = request.headers.get("X-Signature", "")
        if not provided:
            raise HTTPException(status_code=401, detail="Missing X-Signature header")
        
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    def _get_profile_context(self, profile: WebhookProfile | None) -> dict[str, Any]:
        """Extract profile context for LLM injection."""
        if not profile:
            return {}
        
        context = {}
        display_name = profile.display_name or profile.name
        if display_name:
            context["name"] = display_name
        if profile.locale:
            context["locale"] = profile.locale
        if profile.facts:
            context["facts"] = profile.facts
        if profile.preferences:
            context["preferences"] = profile.preferences
        
        return context
    
    def create_app(self) -> FastAPI:
        """Create the FastAPI application."""
        app = FastAPI(
            title=self.__class__.__name__,
            description="LLM-powered webhook example",
        )
        
        @app.get("/")
        async def root():
            """Health check endpoint."""
            return {
                "status": "ok",
                "assistant": self.__class__.__name__,
            }
        
        @app.get("/info")
        async def info():
            """Return assistant metadata."""
            return {
                "name": self.__class__.__name__,
                "system_prompt_preview": self.get_system_prompt()[:200] + "...",
                "model": self.config.model,
            }
        
        @app.post("/")
        async def webhook(request: Request) -> JSONResponse:
            """Main webhook endpoint."""
            body = await request.body()
            self._verify_signature(request, body)
            
            try:
                data = await request.json()
                webhook_request = WebhookRequest(**data)
            except Exception as e:
                logger.warning(f"Failed to parse webhook request: {e}")
                raise HTTPException(status_code=400, detail="Invalid request body")
            
            try:
                response = await self.handle_message(webhook_request)
                return JSONResponse(content=response.model_dump())
            except Exception as e:
                logger.exception(f"Error handling message: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": str(e)},
                )
        
        self._app = app
        return app


def create_app(
    system_prompt: str,
    handler: Any,
    config: WebhookConfig | None = None,
) -> FastAPI:
    """Factory function to create a webhook app from a handler function.
    
    Simpler alternative to subclassing BaseWebhookApp.
    
    Args:
        system_prompt: System prompt for the LLM
        handler: Async function that takes WebhookRequest and returns WebhookResponse
        config: Optional configuration
    
    Example:
        async def handle(request: WebhookRequest) -> WebhookResponse:
            return build_text_response(f"Hello, {request.profile.name}!")
        
        app = create_app("You are a helpful assistant.", handle)
    """
    class HandlerApp(BaseWebhookApp):
        def get_system_prompt(self) -> str:
            return system_prompt
        
        async def handle_message(self, request: WebhookRequest) -> WebhookResponse:
            return await handler(request)
    
    return HandlerApp(config).create_app()

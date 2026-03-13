"""Food Ordering -- Multi-step webhook for Nexo Partner Agent API.

Demonstrates 3 intents:
- menu_browse: Returns food item cards with name, price, dietary labels
- order_build: User specifies items + constraints, returns order summary with actions
- order_track: After approval, returns simulated order status card

Capabilities are simulated (no real restaurant API required).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import os
import time
from typing import Any, AsyncIterator

import litellm
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _configure_vertex_env_defaults() -> None:
    """Map common GCP env vars into LiteLLM Vertex vars when unset."""
    project = (
        os.environ.get("VERTEXAI_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
    )
    location = (
        os.environ.get("VERTEXAI_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GCP_REGION")
    )
    if project:
        os.environ.setdefault("VERTEXAI_PROJECT", project)
    if location:
        os.environ.setdefault("VERTEXAI_LOCATION", location)


_configure_vertex_env_defaults()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "vertex_ai/gemini-2.5-flash")
STREAMING_ENABLED = os.environ.get("STREAMING_ENABLED", "true").lower() == "true"

SCHEMA_VERSION = "2026-03-01"
CAPABILITY_NAME = "food.ordering"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-food-ordering",
    "description": "Food ordering webhook example for menu browse, order build, and delivery tracking.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Assist users through menu discovery, order construction, and status tracking.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["menu_browse", "order_build", "order_track"],
                    "prompt_suggestions": [
                        "I'm hungry - show me what's nearby for delivery",
                        "Order a margherita pizza to my place",
                        "Where's my delivery right now?",
                    ],
                },
            }
        ]
    },
}

# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------


def _verify_signature(secret: str, raw_body: bytes, timestamp: str, signature: str) -> bool:
    if not secret or not timestamp or not signature:
        return False
    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = "sha256=" + hmac_mod.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac_mod.compare_digest(expected, signature)


def _require_signature(request: Request, raw_body: bytes) -> None:
    if not WEBHOOK_SECRET:
        return
    timestamp = request.headers.get("x-timestamp", "")
    signature = request.headers.get("x-signature", "")
    if not _verify_signature(WEBHOOK_SECRET, raw_body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "menu_browse": [
        "menu", "what's available", "what do you have", "show me",
        "vegan", "vegetarian", "gluten-free", "options", "food",
        "dishes", "eat", "hungry", "browse",
    ],
    "order_build": [
        "order", "add", "i want", "i'd like", "get me", "buy",
        "purchase", "cart", "place", "allergy", "allergic", "budget",
        "confirm", "checkout", "build",
    ],
    "order_track": [
        "track", "status", "where is", "how long", "delivery",
        "arriving", "eta", "on the way", "preparing", "delivered",
        "my order",
    ],
}


def detect_intent(message: str) -> str:
    """Detect user intent from message text via keyword counting.

    Priority: order_track > order_build > menu_browse > menu_browse (default).
    """
    text = message.lower()
    counts: dict[str, int] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        counts[intent] = sum(1 for kw in keywords if kw in text)

    # Priority ordering for tie-breaking
    priority = ["order_track", "order_build", "menu_browse"]
    best_intent = max(priority, key=lambda k: counts[k])
    if counts[best_intent] > 0:
        return best_intent

    # Default to menu_browse for ambiguous/unknown messages
    return "menu_browse"


def prompt_suggestions_for_intent(intent: str) -> list[str]:
    if intent == "menu_browse":
        return [
            "Show vegetarian options under $20",
            "What are your top-rated dishes?",
            "Filter to gluten-free items",
        ]
    if intent == "order_build":
        return [
            "Add a dessert to this order",
            "Remove the drink and recalculate",
            "Confirm this order now",
        ]
    if intent == "order_track":
        return [
            "Refresh my delivery status",
            "Contact support about this order",
            "Share courier ETA again",
        ]
    return []


def _build_envelope(
    *,
    text: str,
    intent: str,
    cards: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    task_status: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload_metadata = {"prompt_suggestions": prompt_suggestions_for_intent(intent)}
    if metadata:
        payload_metadata.update(metadata)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error" if task_status in {"failed", "canceled"} else "completed",
        "task": {"id": f"task_food_{intent}", "status": task_status},
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": cards or [],
        "actions": actions or [],
        "artifacts": artifacts or [],
        "metadata": payload_metadata,
    }


# ---------------------------------------------------------------------------
# Simulated menu data
# ---------------------------------------------------------------------------

_MENU_ITEMS: list[dict[str, Any]] = [
    {
        "id": "margherita-pizza",
        "name": "Margherita Pizza",
        "price": 12.99,
        "description": "Classic tomato sauce, fresh mozzarella, basil",
        "dietary": ["vegetarian"],
        "image_url": "https://placehold.co/400x300?text=Margherita+Pizza",
        "category": "Pizza",
    },
    {
        "id": "vegan-burger",
        "name": "Vegan Mushroom Burger",
        "price": 14.50,
        "description": "Portobello mushroom patty, avocado, lettuce, tomato, vegan mayo",
        "dietary": ["vegan", "vegetarian"],
        "image_url": "https://placehold.co/400x300?text=Vegan+Burger",
        "category": "Burgers",
    },
    {
        "id": "grilled-chicken",
        "name": "Grilled Chicken Salad",
        "price": 13.75,
        "description": "Grilled chicken breast, mixed greens, cherry tomatoes, balsamic dressing",
        "dietary": ["gluten-free"],
        "image_url": "https://placehold.co/400x300?text=Chicken+Salad",
        "category": "Salads",
    },
    {
        "id": "pasta-arrabiata",
        "name": "Pasta all'Arrabbiata",
        "price": 11.50,
        "description": "Penne pasta, spicy tomato sauce, garlic, fresh chili",
        "dietary": ["vegan", "vegetarian"],
        "image_url": "https://placehold.co/400x300?text=Pasta+Arrabiata",
        "category": "Pasta",
    },
    {
        "id": "fish-tacos",
        "name": "Fish Tacos (x3)",
        "price": 15.00,
        "description": "Grilled tilapia, cabbage slaw, chipotle crema, lime",
        "dietary": ["gluten-free"],
        "image_url": "https://placehold.co/400x300?text=Fish+Tacos",
        "category": "Tacos",
    },
    {
        "id": "lentil-soup",
        "name": "Red Lentil Soup",
        "price": 8.50,
        "description": "Hearty red lentil soup with cumin and lemon",
        "dietary": ["vegan", "vegetarian", "gluten-free"],
        "image_url": "https://placehold.co/400x300?text=Lentil+Soup",
        "category": "Soups",
    },
]

_ORDER_STATUSES = [
    {"status": "preparing", "label": "Preparing your order", "eta_minutes": 20},
    {"status": "on-the-way", "label": "On the way!", "eta_minutes": 10},
    {"status": "delivered", "label": "Delivered - enjoy your meal!", "eta_minutes": 0},
]


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------


def build_menu_card(filter_dietary: str | None = None) -> dict[str, Any]:
    """Build a menu card showing available items, optionally filtered by dietary label."""
    items = _MENU_ITEMS
    if filter_dietary:
        items = [i for i in items if filter_dietary.lower() in [d.lower() for d in i["dietary"]]]

    fields: list[dict[str, str]] = []
    for item in items:
        dietary_str = " / ".join(item["dietary"]) if item["dietary"] else "No label"
        fields.append({
            "label": f"{item['name']} - ${item['price']:.2f}",
            "value": f"{item['description']} [{dietary_str}]",
        })

    if not fields:
        fields = [{"label": "No items found", "value": f"No items matching '{filter_dietary}' available right now"}]

    subtitle = f"Filtered by: {filter_dietary}" if filter_dietary else "Full menu - all items available"
    return {
        "type": "menu",
        "title": "Today's Menu",
        "subtitle": subtitle,
        "badges": ["Food Ordering", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_order_summary_card(
    items: list[dict[str, Any]],
    total: float,
    notes: str = "",
) -> dict[str, Any]:
    """Build an order summary card with item list and total."""
    fields: list[dict[str, str]] = []
    for item in items:
        fields.append({
            "label": item.get("name", "Item"),
            "value": f"${item.get('price', 0.0):.2f} x {item.get('qty', 1)}",
        })
    fields.append({"label": "Total", "value": f"${total:.2f}"})
    if notes:
        fields.append({"label": "Notes", "value": notes})

    return {
        "type": "order_summary",
        "title": "Your Order",
        "subtitle": "Review and confirm before placing",
        "badges": ["Food Ordering", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_order_status_card(status_index: int = 0) -> dict[str, Any]:
    """Build a simulated order tracking status card."""
    idx = min(status_index, len(_ORDER_STATUSES) - 1)
    status = _ORDER_STATUSES[idx]

    fields: list[dict[str, str]] = [
        {"label": "Status", "value": status["label"]},
    ]
    if status["eta_minutes"] > 0:
        fields.append({"label": "ETA", "value": f"~{status['eta_minutes']} minutes"})
    else:
        fields.append({"label": "ETA", "value": "Delivered!"})

    fields.append({"label": "Order ID", "value": "#FO-2026-0042"})
    fields.append({"label": "Restaurant", "value": "Nexo Kitchen (Simulated)"})

    return {
        "type": "order_status",
        "title": "Order Tracking",
        "subtitle": status["label"],
        "badges": ["Food Ordering", "Simulated"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def _get_display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    name = profile.get("display_name") or profile.get("name") or ""
    return name.strip()


def _extract_dietary_filter(query: str) -> str | None:
    """Extract dietary preference from query text."""
    text = query.lower()
    if "vegan" in text:
        return "vegan"
    if "vegetarian" in text:
        return "vegetarian"
    if "gluten" in text:
        return "gluten-free"
    return None


def _build_demo_order_items() -> tuple[list[dict[str, Any]], float]:
    """Return a demo order with 2 items and computed total."""
    items = [
        {"name": "Margherita Pizza", "price": 12.99, "qty": 1},
        {"name": "Lentil Soup", "price": 8.50, "qty": 1},
    ]
    total = sum(i["price"] * i["qty"] for i in items)
    return items, total


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful food ordering assistant for a simulated restaurant. Help users browse the menu, build their order, and track delivery. Be concise, friendly, and clear. Mention dietary options when relevant. Keep responses brief - the structured cards show the full details."""


async def call_llm(system_prompt: str, user_message: str) -> str:
    """Non-streaming LLM call."""
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "I'm having trouble generating a response right now."


async def stream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream LLM response tokens as SSE events."""
    try:
        response = await litellm.acompletion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                payload = json.dumps({"type": "delta", "text": delta})
                yield f"data: {payload}\n\n"
    except Exception as exc:
        logger.warning("LLM streaming failed: %s", exc)
        error_text = "I'm having trouble generating a response right now."
        payload = json.dumps({"type": "delta", "text": error_text})
        yield f"data: {payload}\n\n"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Food Ordering Webhook")


@app.get("/.well-known/agent.json")
async def agent_card():
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root():
    """Service discovery endpoint."""
    return {
        "service": "webhook-food-ordering-python",
        "description": "Food Ordering webhook -- menu browsing, order building, order tracking.",
        "routes": [
            {"path": "/", "method": "POST", "description": "Main Nexo webhook endpoint (JSON or SSE)"},
            {"path": "/.well-known/agent.json", "method": "GET", "description": "Capability discovery metadata"},
            {"path": "/health", "method": "GET", "description": "Health check"},
            {"path": "/ingest", "method": "POST", "description": "Placeholder for future data ingestion"},
        ],
        "capabilities": [
            {"intent": "menu_browse", "state": "simulated"},
            {"intent": "order_build", "state": "simulated"},
            {"intent": "order_track", "state": "simulated"},
        ],
        "auth": "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
        "schema_version": SCHEMA_VERSION,
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "timestamp": time.time(),
    }


@app.post("/ingest")
async def ingest(request: Request):
    """Placeholder for future data ingestion (menu updates, order data, etc.)."""
    return {"status": "ok", "message": "Ingest endpoint reserved for future use"}


# ---------------------------------------------------------------------------
# Main webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/")
async def webhook(request: Request):
    raw_body = await request.body()
    _require_signature(request, raw_body)

    data = json.loads(raw_body)
    message = data.get("message", {})
    query = message.get("content", "")
    if not query:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    intent = detect_intent(query)
    display_name = _get_display_name(data)

    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    context_block = ""

    if intent == "menu_browse":
        dietary_filter = _extract_dietary_filter(query)
        cards.append(build_menu_card(dietary_filter))
        visible_items = [
            i for i in _MENU_ITEMS
            if not dietary_filter or dietary_filter.lower() in [d.lower() for d in i["dietary"]]
        ]
        context_block = "Available menu items:\n" + "\n".join(
            f"  - {item['name']} (${item['price']:.2f}) [{', '.join(item['dietary'])}]: {item['description']}"
            for item in visible_items
        )
        actions = [
            {"id": "build_order", "type": "primary", "label": "Build My Order", "action": "build_order"},
            {"id": "filter_vegan", "type": "secondary", "label": "Vegan Options", "action": "filter_vegan"},
            {"id": "filter_gluten_free", "type": "secondary", "label": "Gluten-Free Options", "action": "filter_gluten_free"},
        ]
        artifacts = [{"type": "application/json", "name": "menu_items", "data": visible_items[:10]}]

    elif intent == "order_build":
        order_items, total = _build_demo_order_items()
        # Check for budget constraint
        budget_note = ""
        if "budget" in query.lower():
            budget_note = "Budget-conscious selection chosen"
        cards.append(build_order_summary_card(order_items, total, notes=budget_note))
        context_block = (
            f"Order summary:\n"
            + "\n".join(f"  - {i['name']} ${i['price']:.2f} x{i['qty']}" for i in order_items)
            + f"\n  Total: ${total:.2f}"
        )
        actions = [
            {"id": "confirm_order", "type": "primary", "label": "Confirm Order", "action": "confirm_order"},
            {"id": "modify_order", "type": "secondary", "label": "Modify Order", "action": "modify_order"},
        ]
        artifacts = [{"type": "application/json", "name": "order_draft", "data": {"items": order_items, "total": total, "notes": budget_note}}]

    elif intent == "order_track":
        # Cycle through statuses for demo - always start at "preparing"
        cards.append(build_order_status_card(status_index=0))
        context_block = (
            "Order status: Preparing your order\n"
            "Order ID: #FO-2026-0042\n"
            "ETA: ~20 minutes\n"
            "Restaurant: Nexo Kitchen (Simulated)"
        )
        actions = [
            {"id": "refresh_status", "type": "primary", "label": "Refresh Status", "action": "refresh_status"},
            {"id": "contact_support", "type": "secondary", "label": "Contact Support", "action": "contact_support"},
        ]
        artifacts = [{"type": "application/json", "name": "order_status", "data": _ORDER_STATUSES[0]}]

    # Build LLM prompt
    if context_block:
        llm_prompt = f"Context:\n{context_block}\n\nUser message: {query}"
    else:
        llm_prompt = f"User message: {query}"

    system = SYSTEM_PROMPT
    if display_name:
        system += f"\nThe user's name is {display_name}. Address them by name."

    # SSE or JSON
    wants_stream = (
        STREAMING_ENABLED
        and "text/event-stream" in request.headers.get("accept", "")
    )

    if wants_stream:
        prompt_suggestions = prompt_suggestions_for_intent(intent)

        async def _event_stream() -> AsyncIterator[str]:
            yield (
                "event: task.started\ndata: "
                + json.dumps({"task": {"id": f"task_food_{intent}", "status": "in_progress"}})
                + "\n\n"
            )
            prefix = f"Hey {display_name}! " if display_name else ""
            if prefix:
                yield f"data: {json.dumps({'type': 'delta', 'text': prefix})}\n\n"
                yield f"event: task.delta\ndata: {json.dumps({'text': prefix})}\n\n"

            async for event in stream_llm(system, llm_prompt):
                if event.startswith("data:"):
                    try:
                        payload = json.loads(event[len("data:"):].strip())
                    except json.JSONDecodeError:
                        yield event
                        continue
                    if payload.get("type") == "delta":
                        yield event
                        yield f"event: task.delta\ndata: {json.dumps({'text': payload.get('text', '')})}\n\n"
                        continue
                yield event

            for artifact in artifacts:
                yield f"event: task.artifact\ndata: {json.dumps(artifact)}\n\n"

            done_payload = {
                "type": "done",
                **_build_envelope(
                    text=prefix.strip(),
                    intent=intent,
                    cards=cards,
                    actions=actions,
                    artifacts=artifacts,
                    metadata={"prompt_suggestions": prompt_suggestions},
                ),
            }
            yield f"data: {json.dumps(done_payload)}\n\n"
            yield "event: done\ndata: " + json.dumps(done_payload) + "\n\n"

        return StreamingResponse(_event_stream(), media_type="text/event-stream")

    # Non-streaming JSON
    llm_reply = await call_llm(system, llm_prompt)
    if display_name:
        llm_reply = f"Hey {display_name}! {llm_reply}"

    return JSONResponse(
        _build_envelope(
            text=llm_reply,
            intent=intent,
            cards=cards,
            actions=actions,
            artifacts=artifacts,
        )
    )

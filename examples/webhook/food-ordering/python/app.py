"""Food Ordering -- Multi-step webhook for Nexo Partner Agent API.

Demonstrates 3 intents:
- menu_browse: Returns food item cards with name, price, dietary labels
- order_build: User specifies items + constraints, returns order summary with actions
- order_track: After approval, returns simulated order status card

Capabilities are simulated (no real restaurant API required).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add shared utilities to path (works both locally and in Docker container)
_here = Path(__file__).resolve().parent
for _ancestor in [_here.parent.parent, _here]:  # local: ../../shared, container: ./shared
    if (_ancestor / "shared").is_dir():
        sys.path.insert(0, str(_ancestor))
        break

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

from shared.envelope import build_envelope, product_card, status_card, action, artifact
from shared.streaming import stream_with_prefix
from shared.sessions import SessionStore

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
SESSION_DB_URL = os.environ.get("SESSION_DB_URL", os.environ.get("DATABASE_URL", ""))

SCHEMA_VERSION = "2026-03"
CAPABILITY_NAME = "food.ordering"

AGENT_CARD: dict[str, Any] = {
    "name": "nexo-food-ordering",
    "description": "Food commerce webhook example for discovery, basket building, checkout approval, delivery tracking, and reorder.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Assist users through restaurant discovery, menu filtering, order construction, checkout approval, and status tracking.",
                "supports_streaming": True,
                "supports_cancellation": False,
                "metadata": {
                    "intents": ["menu_browse", "order_build", "order_track"],
                    "prompt_suggestions": [
                        "I'm hungry - show me nearby vegetarian delivery for tonight",
                        "Build me a dinner order under EUR 25 and prepare checkout",
                        "Track my delivery and suggest a quick reorder",
                    ],
                    "showcase_family": "food",
                    "showcase_role": "flagship",
                },
            }
        ]
    },
}

# ---------------------------------------------------------------------------
# FastAPI app + session store
# ---------------------------------------------------------------------------

app = FastAPI(title="Food Ordering Webhook")

sessions: SessionStore | None = None


@app.on_event("startup")
async def startup() -> None:
    global sessions
    if SESSION_DB_URL:
        sessions = SessionStore(SESSION_DB_URL)
        await sessions.init()


@app.on_event("shutdown")
async def shutdown() -> None:
    if sessions:
        await sessions.close()


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
        "dishes", "eat", "hungry", "browse", "nearby", "restaurants", "delivery for tonight",
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

    # Discovery-style prompts often mention delivery generically. Treat them as
    # browse unless the user is clearly asking about an existing order's status.
    if any(token in text for token in ["show me", "what's available", "hungry", "nearby", "restaurant"]):
        if not any(token in text for token in ["track", "status", "where is", "eta", "on the way", "my order", "preparing"]):
            return "menu_browse"

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


def prompt_suggestions_for_intent(
    intent: str, profile_segment: str = "generic"
) -> list[str]:
    if intent == "menu_browse":
        if profile_segment == "healthy_vegetarian":
            return [
                "Show vegetarian dinners under EUR 20",
                "Find a high-protein plant-based option",
                "Keep it healthy and delivery-friendly",
            ]
        if profile_segment == "family_grill":
            return [
                "Show family bundles with meat mains",
                "Find a barbecue-style dinner for four",
                "Add crowd-pleasing sides for the table",
            ]
        if profile_segment == "premium_organic":
            return [
                "Show organic chef specials for tonight",
                "Find a refined dinner with a premium dessert",
                "Keep it elegant and locally sourced",
            ]
        if profile_segment == "quick_budget":
            return [
                "Show quick meals under EUR 15",
                "Find the fastest dinner near me",
                "Keep it cheap and filling",
            ]
        return [
            "Show vegetarian options under EUR 20",
            "What are your top-rated dishes?",
            "Filter to gluten-free items",
            "Show vegan options",
        ]
    if intent == "order_build":
        if profile_segment == "healthy_vegetarian":
            return [
                "Swap in a lighter side",
                "Keep this vegetarian and under EUR 20",
                "Confirm this healthy order",
            ]
        if profile_segment == "family_grill":
            return [
                "Add a sharing side for the family",
                "Make this order work for four people",
                "Confirm this family dinner",
            ]
        if profile_segment == "premium_organic":
            return [
                "Upgrade with a premium dessert",
                "Keep this order organic and elevated",
                "Prepare this refined checkout",
            ]
        if profile_segment == "quick_budget":
            return [
                "Trim this order below EUR 15",
                "Keep only the fastest items",
                "Confirm this budget dinner",
            ]
        return [
            "Add a dessert to this order",
            "Remove the drink and recalculate",
            "Confirm this order now",
        ]
    if intent == "order_track":
        if profile_segment == "healthy_vegetarian":
            return [
                "Reorder my vegetarian favorite",
                "Show lighter dinner ideas for tomorrow",
                "Share the latest courier ETA again",
            ]
        if profile_segment == "family_grill":
            return [
                "Reorder the family bundle",
                "Add extra grilled sides next time",
                "Refresh this delivery status",
            ]
        if profile_segment == "premium_organic":
            return [
                "Reorder the organic dinner",
                "Upgrade next time with dessert",
                "Refresh this delivery status",
            ]
        if profile_segment == "quick_budget":
            return [
                "Reorder my low-cost quick meal",
                "Show faster dinners under EUR 15",
                "Refresh this delivery status",
            ]
        return [
            "Refresh my delivery status",
            "Contact support about this order",
            "Share courier ETA again",
        ]
    return []


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
    {
        "id": "garden-salad",
        "name": "Garden Salad",
        "price": 9.25,
        "description": "Crunchy greens, cucumber, herbs, lemon vinaigrette",
        "dietary": ["vegan", "vegetarian", "gluten-free"],
        "image_url": "https://placehold.co/400x300?text=Garden+Salad",
        "category": "Salads",
    },
    {
        "id": "salmon-poke-bowl",
        "name": "Salmon Poke Bowl",
        "price": 18.95,
        "description": "Organic salmon, jasmine rice, pickled vegetables, sesame dressing",
        "dietary": ["organic", "gluten-free"],
        "image_url": "https://placehold.co/400x300?text=Salmon+Poke+Bowl",
        "category": "Bowls",
    },
    {
        "id": "family-grill-platter",
        "name": "Family Grill Platter",
        "price": 24.90,
        "description": "Mixed grilled meats with potatoes, slaw, and chimichurri",
        "dietary": ["meat"],
        "image_url": "https://placehold.co/400x300?text=Family+Grill+Platter",
        "category": "Grill",
    },
    {
        "id": "organic-burrata-salad",
        "name": "Organic Burrata Salad",
        "price": 17.40,
        "description": "Burrata, heirloom tomatoes, basil oil, and seasonal greens",
        "dietary": ["vegetarian", "organic"],
        "image_url": "https://placehold.co/400x300?text=Organic+Burrata+Salad",
        "category": "Starters",
    },
    {
        "id": "sushi-combo",
        "name": "Express Sushi Combo",
        "price": 12.40,
        "description": "Quick sushi set with miso soup and edamame",
        "dietary": ["any"],
        "image_url": "https://placehold.co/400x300?text=Express+Sushi+Combo",
        "category": "Japanese",
    },
]

_RESTAURANTS: list[dict[str, Any]] = [
    {
        "name": "Luzia Kitchen",
        "cuisine": "mediterranean",
        "eta": "20-25 min",
        "delivery_fee": "EUR 1.99",
        "tags": ["vegetarian-friendly", "family bundles"],
        "dining_styles": ["healthy", "family"],
        "budget_levels": ["medium"],
        "dietary_modes": ["vegetarian", "family"],
    },
    {
        "name": "Green Fork",
        "cuisine": "healthy",
        "eta": "15-20 min",
        "delivery_fee": "Free",
        "tags": ["vegan", "gluten-free"],
        "dining_styles": ["healthy", "quick"],
        "budget_levels": ["medium", "low"],
        "dietary_modes": ["vegetarian", "vegan", "gluten-free"],
    },
    {
        "name": "Pizza Porto",
        "cuisine": "italian",
        "eta": "25-30 min",
        "delivery_fee": "EUR 2.49",
        "tags": ["comfort food", "group order"],
        "dining_styles": ["family", "quick"],
        "budget_levels": ["medium", "low"],
        "dietary_modes": ["family", "meat", "vegetarian"],
    },
    {
        "name": "Casa Brasa",
        "cuisine": "brazilian grill",
        "eta": "30-35 min",
        "delivery_fee": "EUR 3.49",
        "tags": ["grilled meats", "family platters"],
        "dining_styles": ["family"],
        "budget_levels": ["medium", "high"],
        "dietary_modes": ["meat", "family"],
    },
    {
        "name": "Atelier Organique",
        "cuisine": "french organic",
        "eta": "35-40 min",
        "delivery_fee": "EUR 4.99",
        "tags": ["organic", "chef specials"],
        "dining_styles": ["fine_dining"],
        "budget_levels": ["high"],
        "dietary_modes": ["organic", "vegetarian"],
    },
    {
        "name": "Tokyo Express",
        "cuisine": "japanese",
        "eta": "12-18 min",
        "delivery_fee": "EUR 0.99",
        "tags": ["quick meals", "budget combos"],
        "dining_styles": ["quick"],
        "budget_levels": ["low"],
        "dietary_modes": ["any", "quick"],
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
        "badges": ["Food Ordering", "Commerce Demo"],
        "fields": fields,
        "metadata": {"capability_state": "simulated"},
    }


def build_restaurant_shortlist_card(
    *,
    cuisine: str | None = None,
    location_hint: str | None = None,
    dietary_filter: str | None = None,
    dining_style: str | None = None,
    budget_preference: str | None = None,
    profile_segment: str = "generic",
) -> dict[str, Any]:
    restaurants = _select_restaurants(
        cuisine=cuisine,
        dietary_filter=dietary_filter,
        dining_style=dining_style,
        budget_preference=budget_preference,
        profile_segment=profile_segment,
    )
    fields: list[dict[str, str]] = []
    for restaurant in restaurants[:3]:
        tags = ", ".join(restaurant["tags"])
        fields.append(
            {
                "label": f"{restaurant['name']} - {restaurant['eta']}",
                "value": f"{restaurant['cuisine'].title()} • {restaurant['delivery_fee']} • {tags}",
            }
        )

    subtitle_bits = []
    if location_hint:
        subtitle_bits.append(f"Near {location_hint}")
    if dietary_filter:
        subtitle_bits.append(f"Filtered for {dietary_filter}")
    if dining_style:
        subtitle_bits.append(f"Matched to {dining_style.replace('_', ' ')} dining")
    if budget_preference:
        subtitle_bits.append(f"Budget: {budget_preference}")
    subtitle = " • ".join(subtitle_bits) if subtitle_bits else "Recommended delivery partners"

    return {
        "type": "restaurant_shortlist",
        "title": "Nearby Delivery Options",
        "subtitle": subtitle,
        "badges": ["Food Ordering", "Commerce Demo"],
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
        "badges": ["Food Ordering", "Commerce Demo"],
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
        "badges": ["Food Ordering", "Commerce Demo"],
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


def _get_profile(data: dict[str, Any]) -> dict[str, Any]:
    profile = data.get("profile") or {}
    return profile if isinstance(profile, dict) else {}


def _get_preferences(data: dict[str, Any]) -> dict[str, Any]:
    preferences = _get_profile(data).get("preferences") or {}
    return preferences if isinstance(preferences, dict) else {}


def _extract_profile_dietary(data: dict[str, Any]) -> str | None:
    profile = _get_profile(data)
    preferences = _get_preferences(data)
    dietary = preferences.get("dietary") or profile.get("dietary_preferences")
    if dietary:
        return str(dietary).strip().lower()

    restrictions = profile.get("dietary_restrictions")
    if isinstance(restrictions, list) and restrictions:
        first = restrictions[0]
        if isinstance(first, str) and first.strip():
            return first.strip().lower()
    return None


def _extract_profile_budget(data: dict[str, Any]) -> str | None:
    budget = _get_preferences(data).get("budget")
    if not budget:
        return None
    return str(budget).strip().lower()


def _extract_profile_cuisine(data: dict[str, Any]) -> str | None:
    preferences = _get_preferences(data)
    value = preferences.get("favorite_cuisine") or preferences.get("cuisine")
    if not value:
        return None
    return str(value).strip().lower()


def _extract_profile_dining_style(data: dict[str, Any]) -> str | None:
    value = _get_preferences(data).get("dining_style")
    if not value:
        return None
    return str(value).strip().lower()


def _extract_location_hint(data: dict[str, Any]) -> str | None:
    profile = _get_profile(data)
    for key in ("city", "region", "country"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_locale(data: dict[str, Any]) -> str:
    profile = _get_profile(data)
    locale = (
        profile.get("locale")
        or profile.get("language")
        or _get_preferences(data).get("language")
        or ""
    )
    return str(locale).strip()


def _localized_prefix(locale: str, display_name: str) -> str:
    if not display_name:
        return ""
    lowered = locale.lower()
    if lowered.startswith("pt"):
        return f"Oi {display_name}! "
    if lowered.startswith("fr"):
        return f"Salut {display_name}! "
    if lowered.startswith("it"):
        return f"Ciao {display_name}! "
    if lowered.startswith("ja"):
        return f"{display_name}さん、こんにちは！ "
    if lowered.startswith("es"):
        return f"Hola {display_name}! "
    if lowered.startswith("de"):
        return f"Hallo {display_name}! "
    return f"Hey {display_name}! "


def _language_instruction(locale: str) -> str:
    if not locale:
        return ""
    return (
        f"\nRespond in the user's preferred language ({locale}) for all free-form text. "
        "Keep item names, numbers, and structured fields readable."
    )


def _build_personalization_metadata(data: dict[str, Any]) -> dict[str, Any]:
    used: dict[str, Any] = {}
    dietary = _extract_profile_dietary(data)
    budget = _extract_profile_budget(data)
    cuisine = _extract_profile_cuisine(data)
    dining_style = _extract_profile_dining_style(data)
    locale = _get_locale(data)
    location_hint = _extract_location_hint(data)
    if dietary:
        used["preferences.dietary"] = dietary
    if budget:
        used["preferences.budget"] = budget
    if cuisine:
        used["preferences.cuisine"] = cuisine
    if dining_style:
        used["preferences.dining_style"] = dining_style
    if locale:
        used["locale"] = locale
    if location_hint:
        used["location_hint"] = location_hint
    missing_optional = [
        key
        for key in [
            "preferences.dietary",
            "preferences.budget",
            "preferences.cuisine",
            "preferences.dining_style",
            "locale",
            "location_hint",
        ]
        if key not in used
    ]
    locale_value = locale or "en"
    return {
        "mode": "profile" if used else "generic",
        "used": used,
        "shared_with_partner": list(used.keys()),
        "not_shared": missing_optional,
        "missing_optional": missing_optional,
        "summary": _build_personalization_summary(used, missing_optional, locale_value),
    }


def _friendly_profile_field(field: str) -> str:
    labels = {
        "preferences.dietary": "dietary preference",
        "preferences.budget": "budget preference",
        "preferences.cuisine": "cuisine preference",
        "preferences.dining_style": "dining style",
        "locale": "language / locale",
        "location_hint": "delivery area",
    }
    return labels.get(field, field)


def _format_shared_fields(used: dict[str, Any]) -> str:
    bits: list[str] = []
    for key in [
        "preferences.dietary",
        "preferences.budget",
        "preferences.cuisine",
        "preferences.dining_style",
        "location_hint",
        "locale",
    ]:
        if key not in used:
            continue
        bits.append(f"{_friendly_profile_field(key)}: {used[key]}")
    return ", ".join(bits)


def _format_missing_fields(fields: list[str]) -> str:
    ordered = [
        field
        for field in [
            "preferences.dietary",
            "preferences.budget",
            "preferences.cuisine",
            "preferences.dining_style",
            "location_hint",
            "locale",
        ]
        if field in fields
    ]
    return ", ".join(_friendly_profile_field(field) for field in ordered)


def _build_personalization_summary(
    used: dict[str, Any], missing_optional: list[str], locale: str
) -> str:
    shared = _format_shared_fields(used)
    missing = _format_missing_fields(missing_optional)
    lowered = locale.lower()

    if lowered.startswith("pt"):
        if used:
            summary = f"Contexto compartilhado com o parceiro: {shared}."
            if missing:
                summary += f" Nao compartilhado ou indisponivel: {missing}."
            return summary
        return "Nenhuma preferencia de perfil foi compartilhada, entao as sugestoes continuam genericas."
    if lowered.startswith("fr"):
        if used:
            summary = f"Contexte partage avec le partenaire : {shared}."
            if missing:
                summary += f" Non partage ou indisponible : {missing}."
            return summary
        return "Aucune preference de profil n'a ete partagee, donc les suggestions restent generiques."
    if lowered.startswith("es"):
        if used:
            summary = f"Contexto compartido con el partner: {shared}."
            if missing:
                summary += f" No compartido o no disponible: {missing}."
            return summary
        return "No se compartieron preferencias de perfil, asi que las sugerencias siguen siendo genericas."
    if lowered.startswith("it"):
        if used:
            summary = f"Contesto condiviso con il partner: {shared}."
            if missing:
                summary += f" Non condiviso o non disponibile: {missing}."
            return summary
        return "Nessuna preferenza del profilo e stata condivisa, quindi i suggerimenti restano generici."
    if lowered.startswith("ja"):
        if used:
            summary = f"Partner to shared context: {shared}."
            if missing:
                summary += f" Not shared or unavailable: {missing}."
            return summary
        return "No profile preferences were shared, so suggestions stay generic."
    if used:
        summary = f"Shared with partner: {shared}."
        if missing:
            summary += f" Not shared or unavailable: {missing}."
        return summary
    return "No saved profile preferences were shared, so suggestions stay generic."


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


def _build_demo_order_items(budget_preference: str | None = None) -> tuple[list[dict[str, Any]], float]:
    """Return a demo order with items adapted to budget preference."""
    if budget_preference == "low":
        items = [
            {"name": "Lentil Soup", "price": 8.50, "qty": 1},
            {"name": "Garden Salad", "price": 9.25, "qty": 1},
        ]
    elif budget_preference == "high":
        items = [
            {"name": "Salmon Poke Bowl", "price": 18.95, "qty": 1},
            {"name": "Margherita Pizza", "price": 12.99, "qty": 1},
        ]
    else:
        items = [
            {"name": "Margherita Pizza", "price": 12.99, "qty": 1},
            {"name": "Lentil Soup", "price": 8.50, "qty": 1},
        ]
    total = sum(i["price"] * i["qty"] for i in items)
    return items, total


def _derive_profile_segment(data: dict[str, Any]) -> str:
    dietary = _extract_profile_dietary(data)
    budget = _extract_profile_budget(data)
    dining_style = _extract_profile_dining_style(data)

    if dining_style == "fine_dining" or budget == "high" or dietary == "organic":
        return "premium_organic"
    if dining_style == "family" or dietary == "meat":
        return "family_grill"
    if dining_style == "quick" or budget == "low":
        return "quick_budget"
    if dining_style == "healthy" or dietary in {"vegetarian", "vegan", "gluten-free"}:
        return "healthy_vegetarian"
    return "generic"


def _restaurant_score(
    restaurant: dict[str, Any],
    *,
    cuisine: str | None,
    dietary_filter: str | None,
    dining_style: str | None,
    budget_preference: str | None,
    profile_segment: str,
) -> int:
    score = 0
    haystack = " ".join(
        [restaurant["cuisine"], *restaurant["tags"], *restaurant.get("dietary_modes", [])]
    ).lower()

    if cuisine and cuisine.lower() in haystack:
        score += 5
    if dietary_filter and dietary_filter.lower() in haystack:
        score += 4
    if dining_style and dining_style in restaurant.get("dining_styles", []):
        score += 4
    if budget_preference and budget_preference in restaurant.get("budget_levels", []):
        score += 2

    if profile_segment == "healthy_vegetarian" and any(
        mode in restaurant.get("dietary_modes", [])
        for mode in ["vegetarian", "vegan", "gluten-free"]
    ):
        score += 3
        if any(term in haystack for term in ["healthy", "vegan"]):
            score += 2
    elif profile_segment == "family_grill" and any(
        mode in restaurant.get("dietary_modes", []) for mode in ["family", "meat"]
    ):
        score += 3
        if any(term in haystack for term in ["grill", "grilled", "barbecue"]):
            score += 2
    elif profile_segment == "premium_organic" and "organic" in restaurant.get(
        "dietary_modes", []
    ):
        score += 3
        if any(term in haystack for term in ["organic", "chef"]):
            score += 2
    elif profile_segment == "quick_budget":
        if "quick" in restaurant.get("dining_styles", []):
            score += 3
        if "low" in restaurant.get("budget_levels", []):
            score += 2

    return score


def _select_restaurants(
    *,
    cuisine: str | None,
    dietary_filter: str | None,
    dining_style: str | None,
    budget_preference: str | None,
    profile_segment: str,
) -> list[dict[str, Any]]:
    ranked = sorted(
        _RESTAURANTS,
        key=lambda restaurant: (
            _restaurant_score(
                restaurant,
                cuisine=cuisine,
                dietary_filter=dietary_filter,
                dining_style=dining_style,
                budget_preference=budget_preference,
                profile_segment=profile_segment,
            ),
            -len(restaurant.get("tags", [])),
        ),
        reverse=True,
    )
    return ranked[:3]


def _build_profile_order_items(profile_segment: str) -> tuple[list[dict[str, Any]], float]:
    if profile_segment == "healthy_vegetarian":
        items = [
            {"name": "Vegan Mushroom Burger", "price": 14.50, "qty": 1},
            {"name": "Garden Salad", "price": 9.25, "qty": 1},
        ]
    elif profile_segment == "family_grill":
        items = [
            {"name": "Family Grill Platter", "price": 24.90, "qty": 1},
            {"name": "Fish Tacos (x3)", "price": 15.00, "qty": 1},
        ]
    elif profile_segment == "premium_organic":
        items = [
            {"name": "Organic Burrata Salad", "price": 17.40, "qty": 1},
            {"name": "Salmon Poke Bowl", "price": 18.95, "qty": 1},
        ]
    elif profile_segment == "quick_budget":
        items = [
            {"name": "Express Sushi Combo", "price": 12.40, "qty": 1},
            {"name": "Red Lentil Soup", "price": 8.50, "qty": 1},
        ]
    else:
        return _build_demo_order_items()
    total = sum(i["price"] * i["qty"] for i in items)
    return items, total


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful food ordering assistant for a simulated commerce flow. Help users discover restaurants, browse the menu, build their order, prepare checkout approval, and track delivery. Be concise, friendly, and clear. Mention dietary options when relevant. Keep responses brief - the structured cards show the full details."""


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


async def stream_llm_chunks(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream LLM response as plain text chunks (no SSE formatting)."""
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
                yield delta
    except Exception as exc:
        logger.warning("LLM streaming failed: %s", exc)
        yield "I'm having trouble generating a response right now."


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/.well-known/agent.json")
async def agent_card():
    """Publish capability metadata for A2A-style discovery."""
    return JSONResponse(AGENT_CARD)


@app.get("/")
async def root():
    """Service discovery endpoint."""
    return {
        "service": "webhook-food-ordering-python",
        "description": "Food commerce webhook -- restaurant discovery, basket building, checkout approval, delivery tracking, and reorder.",
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

    thread_id = data.get("thread", {}).get("id", "")
    session = await sessions.get(thread_id) if sessions else {}

    intent = detect_intent(query)
    display_name = _get_display_name(data)
    locale = _get_locale(data)
    personalization = _build_personalization_metadata(data)
    profile_segment = _derive_profile_segment(data)

    cards: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    context_block = ""

    # Load persisted cart/preferences from session if available
    session_cart: list[dict[str, Any]] = session.get("cart", [])
    session_prefs: dict[str, Any] = session.get("preferences", {})

    if intent == "menu_browse":
        dietary_filter = _extract_dietary_filter(query) or _extract_profile_dietary(data)
        cuisine = _extract_profile_cuisine(data)
        dining_style = _extract_profile_dining_style(data)
        budget_preference = _extract_profile_budget(data)
        location_hint = _extract_location_hint(data)
        selected_restaurants = _select_restaurants(
            cuisine=cuisine,
            dietary_filter=dietary_filter,
            dining_style=dining_style,
            budget_preference=budget_preference,
            profile_segment=profile_segment,
        )
        cards.append(
            build_restaurant_shortlist_card(
                cuisine=cuisine,
                location_hint=location_hint,
                dietary_filter=dietary_filter,
                dining_style=dining_style,
                budget_preference=budget_preference,
                profile_segment=profile_segment,
            )
        )
        explicit_menu_request = any(
            token in query.lower()
            for token in ["menu", "what do you have", "what's available", "dishes"]
        )
        if explicit_menu_request or dietary_filter:
            cards.append(build_menu_card(dietary_filter))
        visible_items = [
            i for i in _MENU_ITEMS
            if not dietary_filter or dietary_filter.lower() in [d.lower() for d in i["dietary"]]
        ]
        context_block = "Available restaurants:\n" + "\n".join(
            f"  - {restaurant['name']} ({restaurant['cuisine']}, {restaurant['eta']}, {restaurant['delivery_fee']})"
            for restaurant in selected_restaurants
        )
        context_block += "\n\nAvailable menu items:\n" + "\n".join(
            f"  - {item['name']} (${item['price']:.2f}) [{', '.join(item['dietary'])}]: {item['description']}"
            for item in visible_items
        )
        if dietary_filter and "preferences.dietary" in personalization["used"]:
            context_block += f"\nSaved dietary preference: {dietary_filter}"
        if cuisine and "preferences.cuisine" in personalization["used"]:
            context_block += f"\nPreferred cuisine: {cuisine}"
        if dining_style and "preferences.dining_style" in personalization["used"]:
            context_block += f"\nPreferred dining style: {dining_style}"
        if budget_preference and "preferences.budget" in personalization["used"]:
            context_block += f"\nBudget preference: {budget_preference}"
        if location_hint and "location_hint" in personalization["used"]:
            context_block += f"\nDelivery area hint: {location_hint}"
        actions = [
            action("build_order", "Build My Order"),
            action("open_restaurant", "Open Restaurant"),
        ]
        artifacts = [
            artifact("application/json", "restaurant_shortlist", selected_restaurants),
            artifact("application/json", "menu_items", visible_items[:10]),
        ]
        # Persist dietary preference to session
        if sessions and dietary_filter:
            session_prefs = {**session_prefs, "dietary": dietary_filter}
            await sessions.update(thread_id, preferences=session_prefs)

    elif intent == "order_build":
        budget_preference = _extract_profile_budget(data)
        if profile_segment == "generic":
            order_items, total = _build_demo_order_items(
                budget_preference=budget_preference
            )
        else:
            order_items, total = _build_profile_order_items(profile_segment)
        # Check for budget constraint
        budget_note = ""
        if "budget" in query.lower():
            budget_note = "Budget-conscious selection chosen"
        elif budget_preference:
            budget_note = f"Adjusted for your {budget_preference} budget preference"
        elif profile_segment == "healthy_vegetarian":
            budget_note = "Built around your vegetarian and healthy profile"
        elif profile_segment == "family_grill":
            budget_note = "Built around your family-style meat preferences"
        elif profile_segment == "premium_organic":
            budget_note = "Built around your premium organic dining profile"
        elif profile_segment == "quick_budget":
            budget_note = "Built around your quick and budget-conscious routine"
        cards.append(build_order_summary_card(order_items, total, notes=budget_note))
        context_block = (
            f"Order summary:\n"
            + "\n".join(f"  - {i['name']} ${i['price']:.2f} x{i['qty']}" for i in order_items)
            + f"\n  Total: ${total:.2f}"
        )
        if budget_note:
            context_block += f"\n  Personalization: {budget_note}"
        actions = [
            action("approve_checkout", "Approve Checkout"),
            action("modify_order", "Modify Order"),
            action("save_favorite", "Save As Favorite"),
        ]
        artifacts = [
            artifact(
                "application/json",
                "checkout_package",
                {
                    "items": order_items,
                    "total": total,
                    "notes": budget_note,
                    "approval_required": True,
                },
            )
        ]
        # Persist cart to session
        if sessions:
            await sessions.update(thread_id, cart=order_items)

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
            action("refresh_status", "Refresh Status"),
            action("reorder_favorites", "Reorder Favorites"),
            action("contact_support", "Contact Support"),
        ]
        artifacts = [
            artifact("application/json", "order_status", _ORDER_STATUSES[0]),
            artifact(
                "application/json",
                "reorder_suggestions",
                _build_profile_order_items(profile_segment)[0][:2],
            ),
        ]

    # Build LLM prompt
    if context_block:
        llm_prompt = f"Context:\n{context_block}\n\nUser message: {query}"
    else:
        llm_prompt = f"User message: {query}"

    system = SYSTEM_PROMPT
    if display_name:
        system += f"\nThe user's name is {display_name}. Address them by name."
    system += _language_instruction(locale)
    if personalization["used"]:
        system += (
            "\nUse the user's saved preferences when relevant. Applied profile context: "
            + json.dumps(personalization["used"], sort_keys=True)
        )
    system += f"\nCurrent profile segment: {profile_segment}."

    prompt_suggestions = prompt_suggestions_for_intent(intent, profile_segment)

    # Record user turn in session history
    if sessions and thread_id:
        await sessions.add_turn(thread_id, "user", query)

    # SSE or JSON
    wants_stream = (
        STREAMING_ENABLED
        and "text/event-stream" in request.headers.get("accept", "")
    )

    if wants_stream:
        prefix = _localized_prefix(locale, display_name)
        envelope = build_envelope(
            cards=cards,
            actions=actions,
            artifacts=artifacts,
            suggestions=prompt_suggestions,
            task_id=f"task_food_{intent}",
            capability=CAPABILITY_NAME,
        )
        # Add personalization and prompt suggestions to envelope metadata
        envelope["metadata"] = {
            "personalization": personalization,
            "prompt_suggestions": prompt_suggestions,
        }

        return StreamingResponse(
            stream_with_prefix(prefix, stream_llm_chunks(system, llm_prompt), envelope),
            media_type="text/event-stream",
        )

    # Non-streaming JSON
    llm_reply = await call_llm(system, llm_prompt)
    prefix = _localized_prefix(locale, display_name)
    if prefix:
        llm_reply = f"{prefix}{llm_reply}"

    # Record assistant turn in session history
    if sessions and thread_id:
        await sessions.add_turn(thread_id, "assistant", llm_reply)

    envelope = build_envelope(
        text=llm_reply,
        cards=cards,
        actions=actions,
        artifacts=artifacts,
        suggestions=prompt_suggestions,
        task_id=f"task_food_{intent}",
        capability=CAPABILITY_NAME,
    )
    envelope["metadata"] = {
        "personalization": personalization,
        "prompt_suggestions": prompt_suggestions,
    }

    return JSONResponse(envelope)

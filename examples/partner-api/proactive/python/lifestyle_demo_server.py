#!/usr/bin/env python3
"""
Lifestyle OS demo webhook server - scenario-driven responses for stakeholder walkthroughs.

Supports multiple demo scenarios selectable via DEMO_SCENARIO env var:
- food_ordering: iFood-style food ordering and delivery flow
- fitness_coaching: Workout planning and health tracking
- travel_planning: Trip planning with restaurant and activity recommendations
- education_tutor: Language learning and study planning
- generic: Echo with structured logging (default)

Stdlib-only, no external dependencies. Runs on port 8080 by default.

Usage:
    DEMO_SCENARIO=food_ordering python lifestyle_demo_server.py
    DEMO_SCENARIO=fitness_coaching PORT=9000 python lifestyle_demo_server.py
"""

import hmac
import hashlib
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", "8080"))
DEMO_SCENARIO = os.environ.get("DEMO_SCENARIO", "generic")


# ---------------------------------------------------------------------------
# Scenario response generators
# ---------------------------------------------------------------------------


def food_ordering_response(content: str, profile: dict, locale: str) -> str:
    """iFood-style food ordering flow."""
    lower = content.lower()
    name = profile.get("name") or profile.get("display_name") or "there"

    if any(w in lower for w in ("order", "dinner", "lunch", "food", "hungry")):
        return (
            f"Hi {name}! I'd love to help you order. "
            f"Based on your location, here are the top restaurants near you:\n\n"
            f"1. Pizzaria Bella Napoli - 4.8 stars, 25 min\n"
            f"2. Sushi House - 4.6 stars, 35 min\n"
            f"3. Burger Joint - 4.5 stars, 20 min\n\n"
            f"Which one sounds good? Or tell me what you're in the mood for."
        )
    if any(w in lower for w in ("pizza", "sushi", "burger", "pasta")):
        return (
            "Great choice! Here's the menu highlights:\n\n"
            "- Margherita Pizza - $12.99\n"
            "- Pepperoni Deluxe - $14.99\n"
            "- Quattro Formaggi - $15.99\n\n"
            "What would you like to order? You can add items and I'll place the order."
        )
    if any(w in lower for w in ("track", "status", "where", "delivery")):
        return (
            "Your order #4521 is on its way!\n\n"
            "Driver: Carlos M.\n"
            "Estimated arrival: 12 minutes\n"
            "Current location: Av. Paulista, 2 blocks away\n\n"
            "I'll notify you when the driver arrives."
        )
    return f"I can help you find restaurants, place orders, or track deliveries. What would you like to do, {name}?"


def fitness_coaching_response(content: str, profile: dict, locale: str) -> str:
    """Fitness coaching and health tracking flow."""
    lower = content.lower()
    name = profile.get("name") or "there"

    if any(w in lower for w in ("workout", "exercise", "train", "gym")):
        return (
            f"Here's your personalized workout for today, {name}:\n\n"
            f"**Upper Body Strength** (45 min)\n"
            f"1. Bench Press - 4x8 @ 70% 1RM\n"
            f"2. Bent-Over Rows - 4x10\n"
            f"3. Overhead Press - 3x8\n"
            f"4. Face Pulls - 3x15\n"
            f"5. Bicep Curls - 3x12\n\n"
            f"Ready to start? I'll track your sets and rest periods."
        )
    if any(w in lower for w in ("meal", "nutrition", "diet", "calorie", "macro")):
        return (
            "Based on your goals, here's your daily target:\n\n"
            "Calories: 2,200 kcal\n"
            "Protein: 165g | Carbs: 220g | Fat: 73g\n\n"
            "Today so far: 1,450 kcal consumed\n"
            "Remaining: 750 kcal\n\n"
            "Want me to suggest meals to hit your targets?"
        )
    if any(w in lower for w in ("progress", "stats", "weight", "track")):
        return (
            "Your progress this week:\n\n"
            "Workouts completed: 4/5\n"
            "Avg calories: 2,150 kcal/day\n"
            "Steps: 8,200 avg/day\n"
            "Weight: 78.2 kg (down 0.3 kg)\n\n"
            "You're on track! Keep it up."
        )
    return f"I can help with workouts, nutrition tracking, or progress reports. What interests you, {name}?"


def travel_planning_response(content: str, profile: dict, locale: str) -> str:
    """Travel planning and recommendation flow."""
    lower = content.lower()
    name = profile.get("name") or "there"
    _country = profile.get("country") or "your area"  # noqa: F841

    if any(w in lower for w in ("trip", "travel", "vacation", "holiday")):
        return (
            f"I'd love to help plan your trip, {name}!\n\n"
            f"Based on your preferences, here are some ideas:\n\n"
            f"1. Barcelona, Spain - Culture + beaches, 5 days from $800\n"
            f"2. Lisbon, Portugal - Food + history, 4 days from $650\n"
            f"3. Tokyo, Japan - Tech + cuisine, 7 days from $1,200\n\n"
            f"Which destination interests you? Or tell me your budget and dates."
        )
    if any(w in lower for w in ("restaurant", "eat", "food", "dinner")):
        return (
            "Here are the best-rated restaurants near your destination:\n\n"
            "1. La Boqueria Tapas - Spanish, $$, 4.9 stars\n"
            "2. El Celler de Can Roca - Fine dining, $$$, 4.8 stars\n"
            "3. Bar Canaletes - Casual, $, 4.7 stars\n\n"
            "Want me to make a reservation?"
        )
    if any(w in lower for w in ("flight", "hotel", "book", "reserve")):
        return (
            "I found these options for you:\n\n"
            "Flights (round trip):\n"
            "- Economy: $450 (LATAM, 1 stop)\n"
            "- Business: $1,200 (Iberia, direct)\n\n"
            "Hotels:\n"
            "- Hotel Arts Barcelona - $180/night, 4.5 stars\n"
            "- W Barcelona - $220/night, 4.7 stars\n\n"
            "Shall I book any of these?"
        )
    return f"I can help plan trips, find restaurants, or book flights and hotels. Where would you like to go, {name}?"


def education_tutor_response(content: str, profile: dict, locale: str) -> str:
    """Language learning and education tutor flow."""
    lower = content.lower()
    name = profile.get("name") or "there"

    if any(w in lower for w in ("learn", "study", "practice", "lesson")):
        return (
            f"Welcome to your study session, {name}!\n\n"
            f"Your current progress:\n"
            f"- Spanish: Level B1 (Intermediate)\n"
            f"- Streak: 12 days\n"
            f"- Words learned: 847\n\n"
            f"Today's lesson: Subjunctive mood\n"
            f"Estimated time: 15 minutes\n\n"
            f"Ready to start?"
        )
    if any(w in lower for w in ("quiz", "test", "check", "review")):
        return (
            "Quick review quiz:\n\n"
            "1. Translate: 'I hope you come to the party'\n"
            "   a) Espero que vienes a la fiesta\n"
            "   b) Espero que vengas a la fiesta\n"
            "   c) Espero que vas a la fiesta\n\n"
            "Reply with a, b, or c."
        )
    if any(w in lower for w in ("plan", "schedule", "goal", "target")):
        return (
            "Your study plan for this week:\n\n"
            "Mon: Vocabulary - Food & Cooking (20 min)\n"
            "Tue: Grammar - Subjunctive (15 min)\n"
            "Wed: Listening - Podcast episode (25 min)\n"
            "Thu: Speaking - Conversation practice (20 min)\n"
            "Fri: Review quiz (10 min)\n\n"
            "This pace will get you to B2 in approximately 3 months."
        )
    return f"I can help with lessons, quizzes, or study planning. What would you like to work on, {name}?"


SCENARIO_HANDLERS = {
    "food_ordering": food_ordering_response,
    "fitness_coaching": fitness_coaching_response,
    "travel_planning": travel_planning_response,
    "education_tutor": education_tutor_response,
}


def get_response(content: str, data: dict) -> str:
    """Route to scenario handler or generic echo."""
    handler = SCENARIO_HANDLERS.get(DEMO_SCENARIO)
    if not handler:
        return f"Echo: {content}"

    profile = data.get("profile", {})
    locale = data.get("locale", "en")
    return handler(content, profile, locale)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


def verify_signature(
    secret: str, raw_body: bytes, timestamp: str, signature: str
) -> bool:
    if not secret or not timestamp or not signature:
        return True
    try:
        signed = f"{timestamp}.{raw_body.decode()}"
        expected = (
            "sha256="
            + hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        )
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


class DemoWebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "status": "ok",
                    "scenario": DEMO_SCENARIO,
                    "port": PORT,
                }
            ).encode()
        )

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        secret = os.environ.get("WEBHOOK_SECRET", "")
        ts = self.headers.get("X-Timestamp", "")
        sig = self.headers.get("X-Signature", "")
        if secret and not verify_signature(secret, raw, ts, sig):
            self.send_response(401)
            self.end_headers()
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"Invalid JSON"}')
            return

        msg = data.get("message", {})
        content = msg.get("content", "") or ""
        event = data.get("event", "")
        profile = data.get("profile", {})
        locale = data.get("locale", "en")

        print(f"[{DEMO_SCENARIO}] [{event}] locale={locale} content={content[:80]}")
        if profile:
            print(
                f"  Profile: name={profile.get('name')}, country={profile.get('country')}"
            )

        reply = get_response(content, data)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "schema_version": "2026-03-01",
                    "status": "success",
                    "content_parts": [{"type": "text", "text": reply}],
                }
            ).encode()
        )

    def log_message(self, format, *args):
        pass  # Suppress default logging, we handle our own


def main():
    server = HTTPServer(("0.0.0.0", PORT), DemoWebhookHandler)
    print("Lifestyle OS Demo Server")
    print(f"  Scenario: {DEMO_SCENARIO}")
    print(f"  Port: {PORT}")
    print(f"  Available scenarios: {', '.join(SCENARIO_HANDLERS.keys())}, generic")
    print(f"  Health check: GET http://localhost:{PORT}/")
    print()
    server.serve_forever()


if __name__ == "__main__":
    main()

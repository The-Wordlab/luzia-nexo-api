from base.app import BaseWebhookApp
from base.contract import WebhookRequest


class _TestApp(BaseWebhookApp):
    def get_system_prompt(self) -> str:
        return "test"

    async def handle_message(self, request):  # pragma: no cover - not used
        raise NotImplementedError


def test_webhook_profile_accepts_nexo_shape() -> None:
    payload = {
        "event": "message_created",
        "app": {"id": "app-1"},
        "thread": {"id": "thread-1"},
        "message": {"role": "user", "content": "hello"},
        "profile": {
            "display_name": "Marta",
            "locale": "es",
            "facts": [{"key": "favorite_food", "value": "sushi"}],
            "preferences": {"tone": "friendly"},
        },
    }

    req = WebhookRequest(**payload)
    assert req.profile is not None
    assert req.profile.display_name == "Marta"
    assert isinstance(req.profile.facts, list)


def test_profile_context_uses_display_name_fallback() -> None:
    payload = {
        "event": "message_created",
        "app": {"id": "app-1"},
        "thread": {"id": "thread-1"},
        "message": {"role": "user", "content": "hello"},
        "profile": {
            "display_name": "Alex",
            "locale": "en",
            "facts": [{"key": "timezone", "value": "UTC"}],
        },
    }

    req = WebhookRequest(**payload)
    app = _TestApp()
    ctx = app._get_profile_context(req.profile)

    assert ctx["name"] == "Alex"
    assert ctx["locale"] == "en"
    assert isinstance(ctx["facts"], list)


def test_a2a_message_shape_text_extraction() -> None:
    """A2A shape: text comes from message.parts."""
    payload = {
        "message": {
            "messageId": "msg-1",
            "contextId": "thread-1",
            "role": "user",
            "parts": [{"type": "text", "text": "hello from A2A"}],
            "metadata": {
                "profile": {"display_name": "Marta", "locale": "es"},
                "locale": "es",
                "app": {"id": "app-1"},
                "thread": {"id": "thread-1"},
            },
        },
    }

    req = WebhookRequest(**payload)
    assert req.get_text() == "hello from A2A"
    assert req.get_thread_id() == "thread-1"

    profile = req.get_profile()
    assert profile is not None
    assert profile.display_name == "Marta"
    assert req.get_locale() == "es"


def test_a2a_message_shape_history_extraction() -> None:
    """A2A shape: history comes from message.metadata.history_tail."""
    payload = {
        "message": {
            "parts": [{"type": "text", "text": "hi"}],
            "metadata": {
                "history_tail": [
                    {"role": "user", "content": "previous"},
                    {"role": "assistant", "content": "response"},
                ],
            },
        },
    }

    req = WebhookRequest(**payload)
    history = req.get_history()
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "previous"

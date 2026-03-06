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

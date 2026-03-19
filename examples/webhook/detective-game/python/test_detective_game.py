"""Tests for the Luzia Detective Game webhook example."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

_APP_DIR = Path(__file__).resolve().parent


class FakeStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.responses: dict[tuple[str, str], dict[str, Any]] = {}

    def load_session(self, thread_id: str) -> dict[str, Any]:
        return json.loads(json.dumps(self.sessions.get(thread_id) or {
            "phase": "briefing",
            "act": "opening",
            "turn_count": 0,
            "visited": [],
            "clues": [],
            "flags": [],
            "ending": "",
            "accused": "",
            "last_move": "briefing",
            "adventure_id": "sky_diamond",
            "locale": "",
            "display_name": "",
        }))

    def save_session(self, thread_id: str, state: dict[str, Any]) -> None:
        self.sessions[thread_id] = json.loads(json.dumps(state))

    def get_processed_response(self, thread_id: str, message_key: str) -> dict[str, Any] | None:
        response = self.responses.get((thread_id, message_key))
        if response is None:
            return None
        return json.loads(json.dumps(response))

    def save_processed_response(self, thread_id: str, message_key: str, response: dict[str, Any]) -> None:
        self.responses[(thread_id, message_key)] = json.loads(json.dumps(response))


def _load_app_module(store: FakeStore):
    module_name = f"detective_game_{uuid.uuid4().hex}"
    import os

    os.environ.pop("DETECTIVE_GAME_DSN", None)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("POSTGRES_DSN", None)
    spec = importlib.util.spec_from_file_location(module_name, _APP_DIR / "app.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    mod.set_store_for_testing(store)
    return mod


def _make_client(store: FakeStore | None = None):
    active_store = store or FakeStore()
    app_module = _load_app_module(active_store)
    return TestClient(app_module.app, raise_server_exceptions=False), app_module


def _sign(secret: str, timestamp: str, body: str) -> str:
    payload = f"{timestamp}.{body}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _payload(content: str, *, thread_id: str = "thread-1", message_id: str = "msg-1", seq: int = 1) -> dict[str, Any]:
    return {
        "event": "message_created",
        "app": {"id": "app-1"},
        "thread": {"id": thread_id},
        "message": {
            "id": message_id,
            "seq": seq,
            "role": "user",
            "content": content,
        },
    }


class TestRoot:
    def test_root_lists_service_and_routes(self, tmp_path):
        client, _ = _make_client()
        data = client.get("/").json()
        assert data["service"] == "webhook-detective-game-python"
        assert any(route["path"] == "/" for route in data["routes"])

    def test_health_ok(self, tmp_path):
        client, _ = _make_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_agent_card_has_detective_capability(self, tmp_path):
        client, _ = _make_client()
        data = client.get("/.well-known/agent.json").json()
        assert data["name"] == "luzia-skydiamond"
        assert data["capabilities"]["items"][0]["name"] == "games.detective"
        assert data["capabilities"]["items"][0]["supports_streaming"] is True


class TestGameLoop:
    def test_webhook_alias_matches_root_behavior(self, tmp_path):
        client, _ = _make_client()
        response = client.post("/webhook", json=_payload("hello detective"))
        data = response.json()
        assert response.status_code == 200
        assert "Sky Diamond" in data["content_parts"][0]["text"]

    def test_sse_returns_done_event_with_envelope(self, tmp_path):
        client, _ = _make_client()
        with client.stream(
            "POST",
            "/",
            json=_payload("hello detective"),
            headers={"Accept": "text/event-stream"},
        ) as response:
            body = response.read().decode()
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "event: task.started" in body
        assert "event: done" in body
        done_line = next(line for line in body.splitlines() if line.startswith("event: done"))
        assert done_line == "event: done"
        done_data = None
        lines = body.splitlines()
        for idx, line in enumerate(lines):
            if line == "event: done" and idx + 1 < len(lines) and lines[idx + 1].startswith("data: "):
                done_data = json.loads(lines[idx + 1][len("data: "):])
                break
        assert done_data is not None
        assert done_data["schema_version"] == "2026-03"
        assert done_data["status"] == "completed"
        assert len(done_data["content_parts"]) >= 1

    def test_intro_starts_with_case_briefing(self, tmp_path):
        client, _ = _make_client()
        response = client.post("/", json=_payload("hello detective"))
        data = response.json()
        assert response.status_code == 200
        assert "Sky Diamond" in data["content_parts"][0]["text"]
        assert "begin case" in data["content_parts"][0]["text"].lower()
        assert data["metadata"]["prompt_suggestions"][0] == "Begin the case"
        assert len(data["cards"]) == 1
        assert data["cards"][0]["title"] == "Sky Diamond"

    def test_begin_case_opens_investigation(self, tmp_path):
        client, _ = _make_client()
        response = client.post(
            "/",
            json={
                **_payload("begin case", message_id="msg-1", seq=1),
                "profile": {"display_name": "Mark"},
            },
        )
        data = response.json()
        assert "observatory" in data["content_parts"][0]["text"].lower()
        assert data["metadata"]["game"]["phase"] == "investigating"
        assert "Inspect the glass dome" in data["metadata"]["prompt_suggestions"]
        assert "Search Celeste's dressing suite" in data["metadata"]["prompt_suggestions"]
        assert len(data["cards"]) == 1
        assert data["cards"][0]["title"] == "Case Objective"

    def test_thread_defaults_to_sky_diamond(self, tmp_path):
        client, app_module = _make_client()
        thread_id = "thread-default"
        client.post("/", json=_payload("hello detective", thread_id=thread_id, message_id="m1", seq=1))
        state = app_module.get_store().load_session(thread_id)
        assert state["adventure_id"] == "sky_diamond"
        assert state["phase"] == "briefing"

    def test_invalid_move_returns_guidance(self, tmp_path):
        client, _ = _make_client()
        client.post("/", json=_payload("begin case", message_id="msg-1", seq=1))
        response = client.post("/", json=_payload("sing a song", message_id="msg-2", seq=2))
        data = response.json()
        assert "not in the casebook" in data["content_parts"][0]["text"].lower()
        assert data["status"] == "completed"
        assert data["cards"] == []

    def test_sky_diamond_can_be_solved(self, tmp_path):
        client, _ = _make_client()
        thread_id = "thread-solve"
        client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        client.post("/", json=_payload("inspect the glass dome", thread_id=thread_id, message_id="m2", seq=2))
        client.post("/", json=_payload("inspect the moon balcony", thread_id=thread_id, message_id="m3", seq=3))
        client.post("/", json=_payload("check the lens room", thread_id=thread_id, message_id="m4", seq=4))
        client.post("/", json=_payload("reconstruct the blackout", thread_id=thread_id, message_id="m5", seq=5))
        client.post("/", json=_payload("inspect the catwalk winch", thread_id=thread_id, message_id="m6", seq=6))
        client.post("/", json=_payload("pressure bruno", thread_id=thread_id, message_id="m7", seq=7))
        response = client.post("/", json=_payload("accuse bruno vale", thread_id=thread_id, message_id="m8", seq=8))
        data = response.json()
        text = data["content_parts"][0]["text"].lower()
        assert "bruno vale did it" in text or "bruno vale" in text
        assert data["metadata"]["game"]["phase"] == "solved"
        assert data["metadata"]["game"]["accusation_ready"] is True
        assert len(data["cards"]) == 1
        assert data["cards"][0]["subtitle"] == "Case closed"

    def test_review_clues_path_stays_playable(self, tmp_path):
        client, _ = _make_client()
        thread_id = "thread-review"
        client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        client.post("/", json=_payload("inspect the glass dome", thread_id=thread_id, message_id="m2", seq=2))
        client.post("/", json=_payload("inspect the moon balcony", thread_id=thread_id, message_id="m3", seq=3))
        client.post("/", json=_payload("check the lens room", thread_id=thread_id, message_id="m4", seq=4))
        response = client.post("/", json=_payload("review clues", thread_id=thread_id, message_id="m5", seq=5))
        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "completed"
        assert "next best move" in data["content_parts"][0]["text"].lower()
        assert "reconstruct the blackout" in data["content_parts"][0]["text"].lower()
        assert len(data["cards"]) == 1
        assert data["cards"][0]["title"] == "Evidence Board"

    def test_sky_diamond_unlocks_twist_and_finale(self, tmp_path):
        client, app_module = _make_client()
        thread_id = "thread-acts"
        client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        client.post("/", json=_payload("inspect the glass dome", thread_id=thread_id, message_id="m2", seq=2))
        client.post("/", json=_payload("inspect the moon balcony", thread_id=thread_id, message_id="m3", seq=3))
        client.post("/", json=_payload("check the lens room", thread_id=thread_id, message_id="m4", seq=4))
        twist = client.post("/", json=_payload("reconstruct the blackout", thread_id=thread_id, message_id="m5", seq=5))
        finale = client.post("/", json=_payload("inspect the catwalk winch", thread_id=thread_id, message_id="m6", seq=6))
        state = app_module.get_store().load_session(thread_id)
        assert twist.json()["metadata"]["game"]["act"] == "twist"
        assert finale.json()["metadata"]["game"]["act"] == "finale"
        assert "timeline_reconstructed" in state["flags"]
        assert "winch_route_found" in state["flags"]

    def test_wrong_accusation_fails_case(self, tmp_path):
        client, _ = _make_client()
        thread_id = "thread-fail"
        client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        client.post("/", json=_payload("inspect the glass dome", thread_id=thread_id, message_id="m2", seq=2))
        client.post("/", json=_payload("inspect the moon balcony", thread_id=thread_id, message_id="m3", seq=3))
        client.post("/", json=_payload("check the lens room", thread_id=thread_id, message_id="m4", seq=4))
        client.post("/", json=_payload("reconstruct the blackout", thread_id=thread_id, message_id="m5", seq=5))
        client.post("/", json=_payload("inspect the catwalk winch", thread_id=thread_id, message_id="m6", seq=6))
        client.post("/", json=_payload("pressure bruno", thread_id=thread_id, message_id="m7", seq=7))
        response = client.post("/", json=_payload("accuse iris bell", thread_id=thread_id, message_id="m8", seq=8))
        data = response.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "wrong_accusation"
        assert data["metadata"]["game"]["phase"] == "failed"

    def test_duplicate_delivery_replays_same_response(self, tmp_path):
        client, app_module = _make_client()
        payload = _payload("hello detective", thread_id="thread-dup", message_id="dup-1", seq=1)
        first = client.post("/", json=payload)
        second = client.post("/", json=payload)
        assert first.json() == second.json()
        store = app_module.get_store()
        state = store.load_session("thread-dup")
        assert state["turn_count"] == 0
        assert state["adventure_id"] == "sky_diamond"

    def test_state_persists_across_clients(self, tmp_path):
        shared_store = FakeStore()
        first_client, _ = _make_client(shared_store)
        thread_id = "thread-persist"
        first_client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        second_client, _ = _make_client(shared_store)
        response = second_client.post("/", json=_payload("inspect the glass dome", thread_id=thread_id, message_id="m2", seq=2))
        data = response.json()
        assert "pedestal" in data["content_parts"][0]["text"].lower() or "cradle" in data["content_parts"][0]["text"].lower()
        assert data["metadata"]["game"]["clue_count"] == 1
        assert len(data["cards"]) == 1
        assert data["cards"][0]["title"] == "Evidence Board"

    def test_move_alias_from_case_content_is_understood(self, tmp_path):
        client, _ = _make_client()
        thread_id = "thread-move-alias"
        client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        response = client.post("/", json=_payload("look at the cradle", thread_id=thread_id, message_id="m2", seq=2))
        data = response.json()
        assert "sugar-glass" in data["content_parts"][0]["text"].lower()

    def test_restart_resets_case(self, tmp_path):
        client, app_module = _make_client()
        thread_id = "thread-restart"
        client.post("/", json=_payload("begin case", thread_id=thread_id, message_id="m1", seq=1))
        client.post("/", json=_payload("inspect the glass dome", thread_id=thread_id, message_id="m2", seq=2))
        response = client.post("/", json=_payload("restart", thread_id=thread_id, message_id="m3", seq=3))
        data = response.json()
        state = app_module.get_store().load_session(thread_id)
        assert "start again" in data["content_parts"][0]["text"].lower() or "principio" in data["content_parts"][0]["text"].lower()
        assert state["phase"] == "briefing"
        assert state["clues"] == []

    def test_change_case_explains_single_case_model(self, tmp_path):
        client, app_module = _make_client()
        thread_id = "thread-change"
        response = client.post("/", json=_payload("change case", thread_id=thread_id, message_id="m1", seq=1))
        data = response.json()
        state = app_module.get_store().load_session(thread_id)
        assert "only one case" in data["content_parts"][0]["text"].lower() or "solo hay un caso" in data["content_parts"][0]["text"].lower()
        assert state["phase"] == "briefing"
        assert state["adventure_id"] == "sky_diamond"

    def test_spanish_locale_is_honored_in_system_text(self, tmp_path):
        client, _ = _make_client()
        response = client.post(
            "/",
            json={
                **_payload("hola"),
                "profile": {"display_name": "Ana", "locale": "es-MX"},
            },
        )
        data = response.json()
        assert "Sky Diamond" in data["content_parts"][0]["text"]
        assert "begin case" in data["content_parts"][0]["text"].lower()


class TestSignature:
    def test_invalid_signature_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "supersecret")
        client, _ = _make_client()
        body = json.dumps(_payload("sky diamond"))
        resp = client.post(
            "/",
            data=body,
            headers={
                "content-type": "application/json",
                "x-timestamp": "1234567890",
                "x-signature": "sha256=bad",
            },
        )
        assert resp.status_code == 401

    def test_valid_signature_accepted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "supersecret")
        client, _ = _make_client()
        body = json.dumps(_payload("sky diamond"))
        signature = _sign("supersecret", "1234567890", body)
        resp = client.post(
            "/",
            data=body,
            headers={
                "content-type": "application/json",
                "x-timestamp": "1234567890",
                "x-signature": signature,
            },
        )
        assert resp.status_code == 200

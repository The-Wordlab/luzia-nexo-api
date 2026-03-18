"""A2A compliance contract tests for webhook examples.

Validates that all importable hosted webhook examples:
1. Publish /.well-known/agent.json with valid structure
2. Include task and capability in response envelopes
3. Use canonical schema_version and task.status

Lightweight examples (no pgvector/psycopg deps) are tested via direct
import. RAG examples are tested via their individual test suites.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Module loading (same pattern as test_card_contract.py)
# ---------------------------------------------------------------------------

WEBHOOK_BASE = Path(__file__).parent.parent
import importlib.util


def _load_app_module(path: Path, filename: str, alias: str):
    """Load a webhook example module by file path."""
    filepath = path / filename
    if not filepath.exists():
        return None
    spec = importlib.util.spec_from_file_location(alias, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


# Lightweight examples (no pgvector/psycopg deps)
LIGHTWEIGHT_EXAMPLES = [
    ("food-ordering", "python", "app.py", "a2a_food_ordering"),
    ("routines", "python", "app.py", "a2a_routines"),
    ("travel-planning", "python", "app.py", "a2a_travel_planning"),
    ("fitness-coach", "python", "app.py", "a2a_fitness_coach"),
    ("language-tutor", "python", "app.py", "a2a_language_tutor"),
]

_loaded_modules: dict[str, Any] = {}

for demo_key, subdir, filename, alias in LIGHTWEIGHT_EXAMPLES:
    module_path = WEBHOOK_BASE / demo_key / subdir
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))
    try:
        mod = _load_app_module(module_path, filename, alias)
        if mod is not None:
            _loaded_modules[demo_key] = mod
    except ImportError:
        pass  # Skip examples with unavailable deps

# Fake LLM so tests don't hit real APIs
FAKE_LLM_TEXT = "A2A compliance check response."

_fake_llm_response = type(
    "R", (), {
        "choices": [
            type("C", (), {
                "message": type("M", (), {"content": FAKE_LLM_TEXT})(),
                "delta": type("D", (), {"content": ""})(),
            })()
        ]
    },
)()


# ---------------------------------------------------------------------------
# Test parameters
# ---------------------------------------------------------------------------

def _make_params():
    params = []
    for demo_key, mod in _loaded_modules.items():
        params.append(pytest.param(demo_key, mod, id=demo_key))
    return params


A2A_CASES = _make_params()


# ---------------------------------------------------------------------------
# A2A agent.json contract assertions
# ---------------------------------------------------------------------------

def _assert_agent_json(data: dict[str, Any], demo_key: str) -> None:
    """Assert /.well-known/agent.json conforms to A2A discovery spec."""
    assert "name" in data, f"[{demo_key}] agent.json missing 'name'"
    assert isinstance(data["name"], str), f"[{demo_key}] agent.json name must be str"

    assert "capabilities" in data, f"[{demo_key}] agent.json missing 'capabilities'"
    caps = data["capabilities"]
    assert isinstance(caps, dict), f"[{demo_key}] capabilities must be dict"
    assert "items" in caps, f"[{demo_key}] capabilities missing 'items'"
    items = caps["items"]
    assert isinstance(items, list), f"[{demo_key}] capabilities.items must be list"
    assert len(items) >= 1, f"[{demo_key}] capabilities.items must have at least 1 entry"

    for item in items:
        assert "name" in item, f"[{demo_key}] capability item missing 'name'"
        assert isinstance(item["name"], str), f"[{demo_key}] capability name must be str"


def _assert_a2a_envelope(data: dict[str, Any], demo_key: str) -> None:
    """Assert response envelope includes A2A canonical fields."""
    # schema_version
    assert data.get("schema_version") == "2026-03", (
        f"[{demo_key}] schema_version must be '2026-03', got {data.get('schema_version')!r}"
    )

    # task object with id and status
    assert "task" in data, f"[{demo_key}] response missing 'task'"
    task = data["task"]
    assert isinstance(task, dict), f"[{demo_key}] task must be dict"
    assert "id" in task, f"[{demo_key}] task missing 'id'"
    assert isinstance(task["id"], str), f"[{demo_key}] task.id must be str"
    assert "status" in task, f"[{demo_key}] task missing 'status'"
    valid_statuses = {"queued", "in_progress", "requires_input", "completed", "failed", "canceled"}
    assert task["status"] in valid_statuses, (
        f"[{demo_key}] task.status={task['status']!r} not in {valid_statuses}"
    )

    # capability object
    assert "capability" in data, f"[{demo_key}] response missing 'capability'"
    cap = data["capability"]
    assert isinstance(cap, dict), f"[{demo_key}] capability must be dict"
    assert "name" in cap, f"[{demo_key}] capability missing 'name'"

    # content_parts: at least one
    assert "content_parts" in data, f"[{demo_key}] response missing 'content_parts'"
    assert isinstance(data["content_parts"], list), f"[{demo_key}] content_parts must be list"
    assert len(data["content_parts"]) >= 1, f"[{demo_key}] content_parts must be non-empty"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("demo_key,app_module", A2A_CASES)
async def test_agent_json_endpoint(demo_key: str, app_module):
    """Each hosted example publishes /.well-known/agent.json."""
    async with AsyncClient(
        transport=ASGITransport(app=app_module.app), base_url="http://test"
    ) as client:
        response = await client.get("/.well-known/agent.json")

    assert response.status_code == 200, (
        f"[{demo_key}] /.well-known/agent.json returned {response.status_code}"
    )
    data = response.json()
    _assert_agent_json(data, demo_key)


@pytest.mark.asyncio
@pytest.mark.parametrize("demo_key,app_module", A2A_CASES)
async def test_response_envelope_a2a_fields(demo_key: str, app_module):
    """Each hosted example includes task and capability in response."""
    payload = {"message": {"content": "Hello, this is a test"}}

    with patch("litellm.acompletion", new=AsyncMock(return_value=_fake_llm_response)):
        async with AsyncClient(
            transport=ASGITransport(app=app_module.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/",
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )

    assert response.status_code == 200, (
        f"[{demo_key}] POST / returned {response.status_code}: {response.text}"
    )
    data = response.json()
    _assert_a2a_envelope(data, demo_key)

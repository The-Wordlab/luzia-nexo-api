from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
WEBHOOK_ROOT = REPO_ROOT / "examples" / "webhook"


HOSTED_DISCOVERY_EXAMPLES = [
    ("fitness-coach", WEBHOOK_ROOT / "fitness-coach" / "python", "app.py", "demo_discovery_fitness"),
    ("travel-planner", WEBHOOK_ROOT / "travel-planner" / "python", "app.py", "demo_discovery_travel_planner"),
    ("language-tutor", WEBHOOK_ROOT / "language-tutor" / "python", "app.py", "demo_discovery_language_tutor"),
    ("routines", WEBHOOK_ROOT / "routines" / "python", "app.py", "demo_discovery_routines"),
    ("food-ordering", WEBHOOK_ROOT / "food-ordering" / "python", "app.py", "demo_discovery_food_ordering"),
    ("travel-planning", WEBHOOK_ROOT / "travel-planning" / "python", "app.py", "demo_discovery_travel_planning"),
    ("news-rag", WEBHOOK_ROOT / "news-rag" / "python", "server.py", "demo_discovery_news_rag"),
    ("sports-rag", WEBHOOK_ROOT / "sports-rag" / "python", "server.py", "demo_discovery_sports_rag"),
    ("travel-rag", WEBHOOK_ROOT / "travel-rag" / "python", "server.py", "demo_discovery_travel_rag"),
    ("football-live", WEBHOOK_ROOT / "football-live" / "python", "server.py", "demo_discovery_football_live"),
]


def _load_module(path: Path, filename: str, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _unload_module(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    for key in list(sys.modules.keys()):
        if key.startswith(module_name):
            del sys.modules[key]
    sys.modules.pop("ingest", None)


@pytest.mark.parametrize(
    ("example_id", "path", "filename", "module_name"),
    HOSTED_DISCOVERY_EXAMPLES,
    ids=[entry[0] for entry in HOSTED_DISCOVERY_EXAMPLES],
)
def test_hosted_demo_discovery_exposes_starter_prompt_suggestions(
    example_id: str,
    path: Path,
    filename: str,
    module_name: str,
):
    sys.path.insert(0, str(path))
    try:
        module = _load_module(path, filename, module_name)
        response = TestClient(module.app, raise_server_exceptions=False).get(
            "/.well-known/agent.json"
        )
        assert response.status_code == 200, example_id
        data = response.json()
        items = data.get("capabilities", {}).get("items", [])
        assert items, f"{example_id} discovery card has no capabilities"
        metadata = items[0].get("metadata", {})
        suggestions = metadata.get("prompt_suggestions")
        assert isinstance(suggestions, list), example_id
        assert suggestions, example_id
        assert all(
            isinstance(item, str) and item.strip() for item in suggestions
        ), example_id
    finally:
        sys.path.remove(str(path))
        _unload_module(module_name)

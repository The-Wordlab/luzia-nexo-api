"""Sky Diamond - a stateful detective webhook for Luzia."""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

try:
    import psycopg
    from psycopg.types.json import Jsonb
except Exception:
    psycopg = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment]

SCHEMA_VERSION = "2026-03"
CAPABILITY_NAME = "games.detective"
GAME_TITLE = "Sky Diamond"
APP_DIR = Path(__file__).resolve().parent
ADVENTURES_DIR = APP_DIR / "adventures"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
POSTGRES_DSN = (
    os.environ.get("DETECTIVE_GAME_DSN")
    or os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_DSN")
    or os.environ.get("PGVECTOR_DSN")
)

AGENT_CARD: dict[str, Any] = {
    "name": "luzia-skydiamond",
    "description": "A stateful detective game where Luzia leads one premium mystery and each chat thread becomes a saved investigation.",
    "url": "/",
    "version": "1",
    "capabilities": {
        "items": [
            {
                "name": CAPABILITY_NAME,
                "description": "Play a deterministic mystery in chat with persistent per-thread state, clue tracking, and accusation endings.",
                "supports_streaming": False,
                "supports_cancellation": False,
                "metadata": {
                    "mode": "game",
                    "prompt_suggestions": [
                        "Sky Diamond",
                        "Begin the case",
                    ],
                    "showcase_family": "games",
                    "showcase_role": "prototype",
                },
            }
        ]
    },
}

INTRO_TEXT = (
    "I am Luzia, and tonight I am not your assistant. I am your detective. "
    "Welcome to Sky Diamond. Open the silver casebook and begin the case. Each thread carries one active investigation at a time."
)

HELP_TEXT = (
    "Use short commands or tap the suggestions. During the case you can inspect locations, "
    "question suspects, review clues, accuse someone, or type `restart`. "
    "Typed chat works too: try `look at the dome`, `question Bruno`, `accuse Iris`, or `change case`."
)

_UI_TRANSLATIONS: dict[str, dict[str, str]] = {
    "es": {
        "select_intro": "Soy Luzia, y esta noche no soy tu asistente. Soy tu detective. Abre el cuaderno plateado y entra en Sky Diamond. Cada hilo puede llevar un caso activo.",
        "choose_cases": "Caso disponible: Sky Diamond.",
        "help": "Usa comandos cortos o toca las sugerencias. Puedes inspeccionar lugares, interrogar sospechosos, revisar pistas, acusar a alguien, escribir `restart` o `change case`.",
        "change_case": "El estante vuelve a abrirse. Elige otra aventura para fijarla a este hilo.",
        "restart": "Caso reiniciado. El estante esta abierto otra vez. Elige una aventura para fijar una nueva investigacion a este hilo.",
        "closed_case": "Ese caso esta cerrado. Escribe `restart` para volver al estante, `change case` para elegir otra aventura o `review clues` para ver el resumen.",
        "invalid_move": "Luzia golpea suavemente el expediente. Ese movimiento no esta en el cuaderno. Prueba un lugar, un sospechoso, `review clues` o `change case`.",
        "too_early": "Demasiado pronto. Luzia cierra el cuaderno plateado con una mano enguantada. Necesitamos mas pruebas antes de acusar a alguien.",
    },
    "fr": {
        "select_intro": "Je suis Luzia, et ce soir je ne suis pas votre assistante. Je suis votre detective. Ouvrez le carnet argente et entrez dans Sky Diamond. Chaque fil peut porter une enquete active.",
        "choose_cases": "Affaire disponible : Sky Diamond.",
        "help": "Utilisez de courtes commandes ou les suggestions. Vous pouvez inspecter des lieux, interroger des suspects, revoir les indices, accuser quelqu'un, ecrire `restart` ou `change case`.",
        "change_case": "L'etagere des dossiers s'ouvre de nouveau. Choisissez une autre aventure pour l'epingler a ce fil.",
        "restart": "Affaire reinitialisee. L'etagere est de nouveau ouverte. Choisissez une aventure pour epingler une nouvelle enquete a ce fil.",
        "closed_case": "Cette affaire est close. Tapez `restart` pour revenir a l'etagere, `change case` pour choisir une autre aventure, ou `review clues` pour le resume.",
        "invalid_move": "Luzia tapote le dossier. Ce mouvement n'est pas dans le carnet. Essayez un lieu, un suspect, `review clues` ou `change case`.",
        "too_early": "Trop tot. Luzia referme le carnet argente d'une main gant ee. Il nous faut plus de preuves avant d'accuser quelqu'un.",
    },
    "pt": {
        "select_intro": "Sou Luzia, e esta noite nao sou sua assistente. Sou sua detetive. Abra o caderno prateado e entre em Sky Diamond. Cada conversa pode carregar um caso ativo.",
        "choose_cases": "Caso disponivel: Sky Diamond.",
        "help": "Use comandos curtos ou toque nas sugestoes. Voce pode inspecionar lugares, interrogar suspeitos, revisar pistas, acusar alguem, digitar `restart` ou `change case`.",
        "change_case": "A estante de casos esta aberta outra vez. Escolha outra aventura para fixar nesta conversa.",
        "restart": "Caso reiniciado. A estante esta aberta outra vez. Escolha uma aventura para fixar uma nova investigacao nesta conversa.",
        "closed_case": "Esse caso esta encerrado. Digite `restart` para voltar a estante, `change case` para escolher outra aventura, ou `review clues` para o resumo.",
        "invalid_move": "Luzia toca o arquivo com a ponta dos dedos. Esse movimento nao esta no caderno. Tente um lugar, um suspeito, `review clues` ou `change case`.",
        "too_early": "Muito cedo. Luzia fecha o caderno prateado com uma mao enluvada. Precisamos de mais provas antes de acusar alguem.",
    },
    "it": {
        "select_intro": "Sono Luzia, e stanotte non sono la tua assistente. Sono la tua detective. Apri il taccuino d'argento ed entra in Sky Diamond. Ogni thread puo contenere un caso attivo.",
        "choose_cases": "Caso disponibile: Sky Diamond.",
        "help": "Usa comandi brevi o i suggerimenti. Puoi ispezionare luoghi, interrogare sospetti, rivedere gli indizi, accusare qualcuno, digitare `restart` o `change case`.",
        "change_case": "Lo scaffale dei casi si riapre. Scegli un'altra avventura da fissare a questo thread.",
        "restart": "Caso azzerato. Lo scaffale e di nuovo aperto. Scegli un'avventura per fissare una nuova indagine a questo thread.",
        "closed_case": "Questo caso e chiuso. Scrivi `restart` per tornare allo scaffale, `change case` per scegliere un'altra avventura, oppure `review clues` per il riepilogo.",
        "invalid_move": "Luzia tocca il fascicolo. Questa mossa non e nel taccuino. Prova un luogo, un sospetto, `review clues` o `change case`.",
        "too_early": "Troppo presto. Luzia chiude il taccuino d'argento con una mano guantata. Ci servono piu prove prima di accusare qualcuno.",
    },
}


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _load_adventures() -> dict[str, dict[str, Any]]:
    adventures: dict[str, dict[str, Any]] = {}
    for path in sorted(ADVENTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        _validate_adventure(data, path)
        adventures[str(data["id"])] = data
    if not adventures:
        raise RuntimeError(f"No adventure files found in {ADVENTURES_DIR}")
    return adventures


def _validate_adventure(adventure: dict[str, Any], path: Path) -> None:
    required = [
        "id",
        "title",
        "hook",
        "objective",
        "setting",
        "tone",
        "briefing",
        "start_text",
        "culprit",
        "suspects",
        "clue_labels",
        "moves",
    ]
    missing = [key for key in required if key not in adventure]
    if missing:
        raise RuntimeError(f"{path.name} is missing required keys: {', '.join(missing)}")
    suspects = adventure["suspects"]
    if adventure["culprit"] not in suspects:
        raise RuntimeError(f"{path.name} culprit must be one of: {', '.join(sorted(suspects))}")
    for move_name, move in adventure["moves"].items():
        if "label" not in move or "visit" not in move or "text" not in move:
            raise RuntimeError(f"{path.name} move {move_name} is missing label, visit, or text")
        clue = move.get("clue")
        if clue is not None and clue not in adventure["clue_labels"]:
            raise RuntimeError(f"{path.name} move {move_name} references unknown clue {clue}")
    for flag in adventure.get("accusation_requires_flags", []):
        if flag not in adventure.get("flag_labels", {}):
            raise RuntimeError(f"{path.name} accusation flag {flag} is missing from flag_labels")


ADVENTURES = _load_adventures()


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    target: str | None = None


class DetectiveStore:
    """Postgres-backed store for sessions and duplicate-delivery replay."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._ensure_schema()

    def _connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is required for the detective game Postgres store")
        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        thread_id TEXT PRIMARY KEY,
                        state_json JSONB NOT NULL,
                        updated_at BIGINT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_messages (
                        thread_id TEXT NOT NULL,
                        message_key TEXT NOT NULL,
                        response_json JSONB NOT NULL,
                        created_at BIGINT NOT NULL,
                        PRIMARY KEY (thread_id, message_key)
                    )
                    """
                )
            conn.commit()

    def load_session(self, thread_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state_json FROM sessions WHERE thread_id = %s", (thread_id,))
                row = cur.fetchone()
        if row is None:
            return new_session_state()
        state_json = row[0]
        state = state_json if isinstance(state_json, dict) else json.loads(state_json)
        return _coerce_state(state)

    def save_session(self, thread_id: str, state: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sessions(thread_id, state_json, updated_at)
                    VALUES(%s, %s, %s)
                    ON CONFLICT(thread_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (thread_id, Jsonb(state), int(time.time())),
                )
            conn.commit()

    def get_processed_response(self, thread_id: str, message_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT response_json
                    FROM processed_messages
                    WHERE thread_id = %s AND message_key = %s
                    """,
                    (thread_id, message_key),
                )
                row = cur.fetchone()
        if row is None:
            return None
        response_json = row[0]
        return response_json if isinstance(response_json, dict) else json.loads(response_json)

    def save_processed_response(self, thread_id: str, message_key: str, response: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO processed_messages(thread_id, message_key, response_json, created_at)
                    VALUES(%s, %s, %s, %s)
                    ON CONFLICT(thread_id, message_key) DO UPDATE SET
                        response_json = excluded.response_json,
                        created_at = excluded.created_at
                    """,
                    (thread_id, message_key, Jsonb(response), int(time.time())),
                )
            conn.commit()


_store_override: Any | None = None
_store_singleton: DetectiveStore | None = None


def set_store_for_testing(store: Any | None) -> None:
    global _store_override, _store_singleton
    _store_override = store
    _store_singleton = None


def get_store() -> Any:
    global _store_singleton
    if _store_override is not None:
        return _store_override
    if not POSTGRES_DSN:
        raise RuntimeError("DETECTIVE_GAME_DSN, DATABASE_URL, or POSTGRES_DSN is required")
    if _store_singleton is None:
        _store_singleton = DetectiveStore(POSTGRES_DSN)
    return _store_singleton


def new_session_state() -> dict[str, Any]:
    return {
        "phase": "select_adventure",
        "act": "",
        "turn_count": 0,
        "visited": [],
        "clues": [],
        "flags": [],
        "ending": "",
        "accused": "",
        "last_move": "briefing",
        "adventure_id": "",
        "locale": "",
        "display_name": "",
    }


def _coerce_state(state: dict[str, Any] | None) -> dict[str, Any]:
    merged = new_session_state()
    if state:
        merged.update(state)
    for key in ["visited", "clues", "flags"]:
        if not isinstance(merged.get(key), list):
            merged[key] = []
    return merged


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
    ts = request.headers.get("x-timestamp", "")
    sig = request.headers.get("x-signature", "")
    if not _verify_signature(WEBHOOK_SECRET, raw_body, ts, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _append_unique(values: list[str], item: str) -> bool:
    if item not in values:
        values.append(item)
        return True
    return False


def _thread_id(data: dict[str, Any]) -> str:
    thread = data.get("thread") or {}
    return str(thread.get("id") or "default-thread")


def _message_key(data: dict[str, Any]) -> str:
    message = data.get("message") or {}
    if message.get("id"):
        return str(message["id"])
    if message.get("seq") is not None:
        return f"seq:{message['seq']}"
    content = str(message.get("content") or "")
    timestamp = str(data.get("timestamp") or "")
    digest = hashlib.sha256(f"{content}|{timestamp}".encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def _display_name(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    return str(profile.get("display_name") or profile.get("name") or "").strip()


def _get_locale(data: dict[str, Any]) -> str:
    profile = data.get("profile") or {}
    locale = profile.get("locale") or profile.get("language") or ""
    return str(locale).strip()


def _language_key(locale: str) -> str:
    return locale.split("-")[0].lower() if locale else ""


def _localized_prefix(locale: str, display_name: str) -> str:
    if not display_name:
        return ""
    lowered = _language_key(locale)
    if lowered == "pt":
        return f"Oi {display_name}! "
    if lowered == "fr":
        return f"Salut {display_name}! "
    if lowered == "it":
        return f"Ciao {display_name}! "
    if lowered == "es":
        return f"Hola {display_name}! "
    return f"Hey {display_name}! "


def _ui_text(state: dict[str, Any], key: str, default: str) -> str:
    locale = _language_key(str(state.get("locale") or ""))
    return _UI_TRANSLATIONS.get(locale, {}).get(key, default)


def _current_adventure(state: dict[str, Any]) -> dict[str, Any] | None:
    adventure_id = state.get("adventure_id") or ""
    return ADVENTURES.get(adventure_id)


def _ordered_adventures() -> list[dict[str, Any]]:
    return list(ADVENTURES.values())


def _act_title(state: dict[str, Any]) -> str:
    adventure = _current_adventure(state)
    if adventure is None:
        return "Case Shelf"
    act = state.get("act") or adventure.get("initial_act", "opening")
    return adventure.get("act_titles", {}).get(act, act.replace("_", " ").title())


def _move_aliases(move_name: str, move: dict[str, Any]) -> list[str]:
    aliases = [_normalize(str(move.get("label") or ""))]
    aliases.extend(_normalize(str(alias)) for alias in move.get("aliases", []))
    aliases.append(_normalize(move_name.replace("_", " ")))
    return [alias for alias in aliases if alias]


def _move_available(state: dict[str, Any], move_name: str, move: dict[str, Any]) -> bool:
    if state["phase"] != "investigating":
        return False
    required_flags = move.get("requires_flags", [])
    if any(flag not in state["flags"] for flag in required_flags):
        return False
    required_clues = move.get("requires_clues", [])
    if any(clue not in state["clues"] for clue in required_clues):
        return False
    required_visited = move.get("requires_visited", [])
    if any(visit not in state["visited"] for visit in required_visited):
        return False
    required_act = move.get("required_act")
    if required_act and state.get("act") != required_act:
        return False
    min_clues = int(move.get("min_clues", 0))
    if len(state["clues"]) < min_clues:
        return False
    return True


def _available_move_names(state: dict[str, Any], *, include_repeat: bool = True) -> list[str]:
    adventure = _current_adventure(state)
    if adventure is None:
        return []
    names: list[str] = []
    for move_name, move in adventure["moves"].items():
        if not _move_available(state, move_name, move):
            continue
        if not include_repeat and move.get("clue") in state["clues"]:
            continue
        names.append(move_name)
    return names


def _prioritized_move_names(state: dict[str, Any], *, include_repeat: bool = True) -> list[str]:
    adventure = _current_adventure(state)
    if adventure is None:
        return []
    available = _available_move_names(state, include_repeat=include_repeat)
    visited = set(state.get("visited") or [])

    def sort_key(move_name: str) -> tuple[int, int, int, str]:
        move = adventure["moves"][move_name]
        clue = move.get("clue")
        has_unlocks = 0 if move.get("unlocks") else 1
        unseen = 0 if move["visit"] not in visited else 1
        gives_new_clue = 0 if clue and clue not in state["clues"] else 1
        return (has_unlocks, gives_new_clue, unseen, move["label"])

    return sorted(available, key=sort_key)


def _accusation_ready(state: dict[str, Any]) -> bool:
    adventure = _current_adventure(state)
    if adventure is None:
        return False
    if len(state["clues"]) < int(adventure.get("accusation_threshold", 3)):
        return False
    return all(flag in state["flags"] for flag in adventure.get("accusation_requires_flags", []))


def parse_command(message: str, state: dict[str, Any] | None = None) -> ParsedCommand:
    text = (message or "").strip().lower()
    if not text:
        return ParsedCommand("help")
    if text in {"help", "hint", "commands"} or "what can i do" in text:
        return ParsedCommand("help")
    if "change case" in text or "switch case" in text or "choose another" in text or "back to cases" in text:
        return ParsedCommand("change_case")
    if text in {"restart", "reset", "new game", "start over"}:
        return ParsedCommand("restart")
    if "recap" in text or "summary" in text:
        return ParsedCommand("review_case")
    if any(token in text for token in {"begin", "start", "play", "open case"}) and "case" in text:
        return ParsedCommand("begin_case")
    if "inventory" in text or "clue" in text or "review" in text or "case file" in text:
        return ParsedCommand("review_case")

    normalized = _normalize(text)
    for adventure_id, adventure in ADVENTURES.items():
        aliases = [_normalize(adventure["title"]), adventure_id.replace("_", " ")]
        aliases.extend(_normalize(alias) for alias in adventure.get("aliases", []))
        if any(alias and alias in normalized for alias in aliases):
            return ParsedCommand("select_adventure", adventure_id)

    if "accuse" in text or "blame" in text:
        if "bruno" in text:
            return ParsedCommand("accuse", "bruno")
        if "iris" in text:
            return ParsedCommand("accuse", "iris")
        if "celeste" in text:
            return ParsedCommand("accuse", "celeste")
        return ParsedCommand("accuse", "unknown")

    if state is not None:
        adventure = _current_adventure(state)
        if adventure is not None:
            for move_name in _available_move_names(state) + list(adventure["moves"].keys()):
                move = adventure["moves"][move_name]
                if any(alias and alias in normalized for alias in _move_aliases(move_name, move)):
                    return ParsedCommand("move", move_name)

    return ParsedCommand("unknown")


def _available_suggestions(state: dict[str, Any]) -> list[str]:
    adventure = _current_adventure(state)
    if state["phase"] == "select_adventure" or adventure is None:
        return [case["title"] for case in _ordered_adventures()] + ["Help"]
    if state["phase"] == "briefing":
        return ["Begin the case", "Change case", "Help", "Restart"]
    if state["phase"] in {"solved", "failed"}:
        return ["Restart", "Review clues", "Change case", "Begin the case"]

    if _accusation_ready(state):
        return [
            "Accuse Bruno Vale",
            "Accuse Iris Bell",
            "Accuse Celeste Rowan",
            "Review clues",
            "Change case",
        ]

    move_names = _prioritized_move_names(state, include_repeat=False)
    if not move_names:
        move_names = _prioritized_move_names(state)
    labels = [adventure["moves"][name]["label"] for name in move_names[:5]]
    if len(labels) < 5:
        labels.append("Review clues" if state["clues"] else "Help")
    return labels[:5]


def _actions_for_suggestions(suggestions: list[str]) -> list[dict[str, str]]:
    return [
        {
            "id": f"action_{index + 1}",
            "label": suggestion,
            "style": "primary" if index == 0 else "secondary",
        }
        for index, suggestion in enumerate(suggestions)
    ]


def _completion_percent(state: dict[str, Any]) -> int:
    adventure = _current_adventure(state)
    if adventure is None:
        return 0
    total = max(len(adventure["clue_labels"]) + len(adventure.get("flag_labels", {})), 1)
    progress = len(state["clues"]) + len(state["flags"])
    return min(100, int((progress / total) * 100))


def _selection_card() -> dict[str, Any]:
    return {
        "type": "info",
        "title": GAME_TITLE,
        "subtitle": "One Premium Case",
        "description": "A stateful detective mystery built for one pinned chat thread.",
        "badges": ["Game", "Detective", "Flagship"],
        "fields": [
            {
                "label": adventure["title"],
                "value": f"{adventure['hook']} Tone: {adventure.get('tone', 'Mystery')}.",
            }
            for adventure in _ordered_adventures()
        ],
        "metadata": {"capability_state": "live"},
    }


def _case_card(state: dict[str, Any]) -> dict[str, Any]:
    adventure = _current_adventure(state)
    if adventure is None:
        return _selection_card()

    subtitle = _act_title(state)
    if state["phase"] == "solved":
        subtitle = "Case closed"
    elif state["phase"] == "failed":
        subtitle = "Wrong accusation"

    clue_lines = [adventure["clue_labels"][key] for key in state["clues"]] or ["No evidence logged yet"]
    return {
        "type": "info",
        "title": adventure["title"],
        "subtitle": subtitle,
        "description": adventure["hook"],
        "badges": ["Game", "Detective", "Classic IF"],
        "fields": [
            {"label": "Phase", "value": state["phase"].title()},
            {"label": "Act", "value": _act_title(state)},
            {"label": "Turns", "value": str(state["turn_count"])},
            {"label": "Clues", "value": str(len(state["clues"]))},
            {"label": "Evidence", "value": " | ".join(clue_lines[:3])},
        ],
        "metadata": {"capability_state": "live"},
    }


def _objective_card(state: dict[str, Any]) -> dict[str, Any]:
    adventure = _current_adventure(state)
    if adventure is None:
        return {
            "type": "info",
            "title": "How To Play",
            "subtitle": "One case per thread",
            "fields": [
                {"label": "Open", "value": "Enter Sky Diamond from the case shelf."},
                {"label": "Pin", "value": "This thread stays on Sky Diamond until `change case`."},
                {"label": "Solve", "value": "Collect clues, unlock the reveal, and make the final accusation."},
            ],
            "metadata": {"capability_state": "live"},
        }

    act = state.get("act") or adventure.get("initial_act", "opening")
    objective = adventure.get("act_objectives", {}).get(act, adventure["objective"])
    total_clues = len(adventure["clue_labels"])
    return {
        "type": "info",
        "title": "Case Objective",
        "subtitle": adventure.get("setting", adventure["title"]),
        "fields": [
            {"label": "Objective", "value": objective},
            {"label": "Tone", "value": adventure.get("tone", "Mystery")},
            {"label": "Progress", "value": f"{_completion_percent(state)}%"},
            {"label": "Evidence mapped", "value": f"{len(state['clues'])}/{total_clues}"},
        ],
        "metadata": {"capability_state": "live"},
    }


def _suspect_card(state: dict[str, Any]) -> dict[str, Any]:
    adventure = _current_adventure(state)
    if adventure is None:
        return {
            "type": "info",
            "title": "Pinned Thread",
            "subtitle": "No case selected yet",
            "fields": [
                {"label": "How pinning works", "value": "Once you open Sky Diamond, this thread stays pinned to it until `change case` or a fresh thread."}
            ],
            "metadata": {"capability_state": "live"},
        }

    suspect_notes = {
        "bruno": adventure["suspects"]["bruno"],
        "iris": adventure["suspects"]["iris"],
        "celeste": adventure["suspects"]["celeste"],
    }
    for suspect, updates in adventure.get("suspect_updates", {}).items():
        for clue_key, update in updates.items():
            if clue_key in state["clues"]:
                suspect_notes[suspect] = update
    if state["phase"] == "solved":
        culprit = state.get("accused") or adventure["culprit"]
        suspect_notes[str(culprit)] = "Culprit: the case is closed"

    return {
        "type": "info",
        "title": "Suspect Board",
        "subtitle": "Three suspects. One impossible crime.",
        "fields": [
            {"label": "Bruno Vale", "value": suspect_notes["bruno"]},
            {"label": "Iris Bell", "value": suspect_notes["iris"]},
            {"label": "Celeste Rowan", "value": suspect_notes["celeste"]},
        ],
        "metadata": {"capability_state": "live"},
    }


def _evidence_card(state: dict[str, Any]) -> dict[str, Any]:
    adventure = _current_adventure(state)
    if adventure is None:
        return {
            "type": "info",
            "title": "Case Shelf",
            "subtitle": "Pinned adventures are easy to switch",
            "fields": [
                {"label": "Command", "value": "`change case` returns you here without opening a new thread."}
            ],
            "metadata": {"capability_state": "live"},
        }

    discovered = [adventure["clue_labels"][key] for key in state["clues"]]
    visited = state.get("visited") or []
    remaining = max(len(adventure["clue_labels"]) - len(state["clues"]), 0)
    return {
        "type": "info",
        "title": "Evidence Board",
        "subtitle": "Clues and scene coverage",
        "fields": [
            {"label": "Evidence logged", "value": " | ".join(discovered[:3]) if discovered else "No evidence logged yet"},
            {"label": "Visited scenes", "value": " | ".join(visit.replace("_", " ").title() for visit in visited[:4]) if visited else "No scenes visited yet"},
            {"label": "Clues remaining", "value": str(remaining)},
            {"label": "Case momentum", "value": "Accusation ready" if _accusation_ready(state) else "Still building"},
        ],
        "metadata": {"capability_state": "live"},
    }


def _revelation_card(state: dict[str, Any]) -> dict[str, Any]:
    adventure = _current_adventure(state)
    if adventure is None:
        return {
            "type": "info",
            "title": "Casebook",
            "subtitle": "Typed chat works too",
            "fields": [
                {"label": "Example", "value": "Try `inspect the glass dome`, `review clues`, or `accuse Bruno Vale`."}
            ],
            "metadata": {"capability_state": "live"},
        }

    flag_labels = adventure.get("flag_labels", {})
    revelations = [flag_labels[flag] for flag in state["flags"] if flag in flag_labels]
    if not revelations:
        revelations = ["No major reveal yet. The case is still gathering shape."]
    return {
        "type": "info",
        "title": "Revelations",
        "subtitle": _act_title(state),
        "fields": [
            {"label": f"Reveal {index + 1}", "value": revelation}
            for index, revelation in enumerate(revelations[:3])
        ],
        "metadata": {"capability_state": "live"},
    }


def _response(*, text: str, state: dict[str, Any], error: dict[str, Any] | None = None) -> dict[str, Any]:
    adventure = _current_adventure(state)
    suggestions = _available_suggestions(state)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed" if error is None else "error",
        "task": {
            "id": f"task_detective_{state['phase']}",
            "status": "completed" if error is None else "failed",
        },
        "capability": {"name": CAPABILITY_NAME, "version": "1"},
        "content_parts": [{"type": "text", "text": text}],
        "cards": [
            _case_card(state),
            _objective_card(state),
            _suspect_card(state),
            _evidence_card(state),
            _revelation_card(state),
        ],
        "actions": _actions_for_suggestions(suggestions),
        "metadata": {
            "prompt_suggestions": suggestions,
            "game": {
                "title": adventure["title"] if adventure is not None else GAME_TITLE,
                "phase": state["phase"],
                "act": state.get("act") or "",
                "clue_count": len(state["clues"]),
                "flag_count": len(state["flags"]),
                "adventure_id": state.get("adventure_id") or "",
                "completion_percent": _completion_percent(state),
                "accusation_ready": _accusation_ready(state),
            },
        },
    }
    if error is not None:
        payload["error"] = error
    return payload


def _mark_turn(state: dict[str, Any], visit_key: str | None = None) -> None:
    state["turn_count"] += 1
    if visit_key:
        _append_unique(state["visited"], visit_key)
        state["last_move"] = visit_key


def _fresh_state_from(state: dict[str, Any]) -> dict[str, Any]:
    new_state = new_session_state()
    new_state["locale"] = str(state.get("locale") or "")
    new_state["display_name"] = str(state.get("display_name") or "")
    return new_state


def _apply_unlocks(state: dict[str, Any], move: dict[str, Any]) -> str:
    unlocks = move.get("unlocks") or {}
    text = ""
    for flag in unlocks.get("flags", []):
        _append_unique(state["flags"], flag)
    if unlocks.get("act"):
        state["act"] = str(unlocks["act"])
    if unlocks.get("text"):
        text = str(unlocks["text"])
    return text


def _run_move(state: dict[str, Any], move_name: str) -> dict[str, Any]:
    adventure = _current_adventure(state)
    assert adventure is not None
    move = adventure["moves"][move_name]
    _mark_turn(state, move["visit"])
    clue_id = move.get("clue")
    first_discovery = clue_id is not None and clue_id not in state["clues"]
    if clue_id and first_discovery:
        _append_unique(state["clues"], clue_id)
        text = move["text"]
    else:
        text = move.get("repeat_text", move["text"])
    unlock_text = _apply_unlocks(state, move) if first_discovery or not move.get("clue") else ""
    if unlock_text:
        text = f"{text} {unlock_text}"
    return _response(text=text, state=state)


def _select_adventure(state: dict[str, Any], adventure_id: str) -> dict[str, Any]:
    adventure = ADVENTURES[adventure_id]
    state["adventure_id"] = adventure_id
    state["phase"] = "briefing"
    state["act"] = adventure.get("initial_act", "opening")
    state["turn_count"] = 0
    state["visited"] = []
    state["clues"] = []
    state["flags"] = []
    state["ending"] = ""
    state["accused"] = ""
    state["last_move"] = "briefing"
    return _response(
        text=f"{adventure['title']}. {adventure['briefing']} Type `begin case` when you are ready, or `change case` to go back.",
        state=state,
    )


def _begin_case(state: dict[str, Any], player_name: str) -> dict[str, Any]:
    adventure = _current_adventure(state)
    assert adventure is not None
    state["phase"] = "investigating"
    _mark_turn(state, "briefing")
    greeting = _localized_prefix(str(state.get("locale") or ""), player_name)
    return _response(text=f"{greeting}{adventure['start_text']}", state=state)


def _review_case(state: dict[str, Any]) -> dict[str, Any]:
    _mark_turn(state, "review")
    adventure = _current_adventure(state)
    assert adventure is not None
    if not state["clues"]:
        text = "No usable clues yet. Work the rooms, question the suspects, and treat every theatrical flourish as camouflage."
        return _response(text=text, state=state)

    discovered = [adventure["clue_labels"][key] for key in state["clues"]]
    open_moves = [
        adventure["moves"][name]["label"]
        for name in _prioritized_move_names(state, include_repeat=False)
        if name != "question_celeste"
    ]
    next_move = ", ".join(open_moves[:2]) if open_moves else "Make your accusation"
    revelations = [adventure.get("flag_labels", {}).get(flag, flag) for flag in state["flags"]]
    reveal_line = f" Major reveals: {'; '.join(revelations)}." if revelations else ""
    act = state.get("act") or adventure.get("initial_act", "opening")
    review_focus = adventure.get("review_templates", {}).get(act, "")
    focus_line = f" {review_focus}" if review_focus else ""
    text = (
        f"Case review: {len(state['clues'])} clues logged. {_act_title(state)}. "
        f"{adventure['hook']}{focus_line} Logged evidence: {'; '.join(discovered)}.{reveal_line} "
        f"Next best move: {next_move}."
    )
    return _response(text=text, state=state)


def _accuse(state: dict[str, Any], target: str | None) -> dict[str, Any]:
    _mark_turn(state, "accusation")
    adventure = _current_adventure(state)
    assert adventure is not None
    threshold = int(adventure.get("accusation_threshold", 3))
    required_flags = adventure.get("accusation_requires_flags", [])
    if len(state["clues"]) < threshold or any(flag not in state["flags"] for flag in required_flags):
        return _response(
            text=_ui_text(
                state,
                "too_early",
                "Too early. Luzia closes the silver casebook with one gloved hand. We need more proof before we accuse anyone.",
            ),
            state=state,
            error={
                "code": "not_enough_evidence",
                "message": "Collect more clues and complete the key reveal before accusing a suspect.",
                "retryable": False,
            },
        )

    state["accused"] = target or "unknown"
    if target == adventure["culprit"]:
        state["phase"] = "solved"
        state["ending"] = "solved"
        text = f"{adventure['solve_text']} Luzia smiles once, closes the casebook, and marks the thread as solved."
        return _response(text=text, state=state)

    state["phase"] = "failed"
    state["ending"] = "failed"
    suspect_name = {
        "iris": "Iris Bell",
        "celeste": "Celeste Rowan",
        "bruno": "Bruno Vale",
        "unknown": "that suspect",
        None: "that suspect",
    }.get(target, str(target).title())
    text = (
        f"You accuse {suspect_name}. Luzia lets the silence land, then shakes her head. "
        "The timeline does not hold and the machinery still hums with the real architect's fingerprints. "
        "Restart the case if you want another run."
    )
    return _response(
        text=text,
        state=state,
        error={
            "code": "wrong_accusation",
            "message": "That accusation does not fit the evidence collected.",
            "retryable": False,
        },
    )


def process_turn(state: dict[str, Any], command: ParsedCommand, player_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if command.name == "restart":
        next_state = _fresh_state_from(state)
        return next_state, _response(
            text=_ui_text(
                next_state,
                "restart",
                "Case reset. The shelf is open again. Choose an adventure to pin this thread to a new investigation.",
            ),
            state=next_state,
        )

    if command.name == "change_case":
        next_state = _fresh_state_from(state)
        return next_state, _response(
            text=_ui_text(
                next_state,
                "change_case",
                "The case shelf opens again. Choose another adventure to pin to this thread.",
            ),
            state=next_state,
        )

    if command.name == "help":
        return state, _response(text=_ui_text(state, "help", HELP_TEXT), state=state)

    if state["phase"] == "select_adventure":
        if command.name == "select_adventure" and command.target in ADVENTURES:
            return state, _select_adventure(state, command.target)
        return state, _response(
            text=(
                f"{_ui_text(state, 'select_intro', INTRO_TEXT)} "
                f"{_ui_text(state, 'choose_cases', 'Case available: Sky Diamond.')}"
            ),
            state=state,
        )

    if state["phase"] == "briefing":
        if command.name == "select_adventure" and command.target in ADVENTURES:
            return state, _select_adventure(state, command.target)
        if command.name == "begin_case":
            return state, _begin_case(state, player_name)
        adventure = _current_adventure(state)
        assert adventure is not None
        return state, _response(text=f"{adventure['briefing']} {HELP_TEXT}", state=state)

    if state["phase"] in {"solved", "failed"}:
        if command.name == "review_case":
            return state, _review_case(state)
        if command.name == "select_adventure" and command.target in ADVENTURES:
            fresh_state = _fresh_state_from(state)
            return fresh_state, _select_adventure(fresh_state, command.target)
        return state, _response(
            text=_ui_text(
                state,
                "closed_case",
                "That case is closed. Type `restart` to reopen the shelf, `change case` to pick another adventure, or `review clues` for the summary.",
            ),
            state=state,
        )

    if command.name == "review_case":
        return state, _review_case(state)
    if command.name == "accuse":
        return state, _accuse(state, command.target)
    if command.name == "move" and command.target:
        adventure = _current_adventure(state)
        assert adventure is not None
        move = adventure["moves"].get(command.target)
        if move and _move_available(state, command.target, move):
            return state, _run_move(state, command.target)
    return state, _response(
        text=_ui_text(
            state,
            "invalid_move",
            "Luzia taps the file. That move is not in the casebook. Try a location, question a suspect, review clues, accuse someone, or type `change case`.",
        ),
        state=state,
    )


app = FastAPI(title="luzia-skydiamond")


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "webhook-detective-game-python",
            "description": "Stateful detective webhook where Luzia leads a single flagship mystery inside a chat thread.",
            "schema_version": SCHEMA_VERSION,
            "routes": [
                {"path": "/", "method": "POST", "description": "Main webhook endpoint"},
                {"path": "/health", "method": "GET", "description": "Health check"},
                {"path": "/.well-known/agent.json", "method": "GET", "description": "Agent metadata"},
            ],
            "capabilities": [
                {
                    "intent": "play_detective_game",
                    "state": "live",
                    "description": "Persistent thread-based mystery game with clue tracking, pinned state, and accusation endings.",
                }
            ],
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "timestamp": int(time.time()), "service": "detective-game"})


@app.get("/.well-known/agent.json")
async def agent_card() -> JSONResponse:
    return JSONResponse(AGENT_CARD)


@app.post("/")
async def webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    _require_signature(request, raw_body)

    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc

    thread_id = _thread_id(data)
    message_key = _message_key(data)
    store = get_store()
    duplicate = store.get_processed_response(thread_id, message_key)
    if duplicate is not None:
        return JSONResponse(duplicate)

    state = _coerce_state(store.load_session(thread_id))
    locale = _get_locale(data)
    display_name = _display_name(data)
    if locale:
        state["locale"] = locale
    if display_name:
        state["display_name"] = display_name
    command = parse_command(str((data.get("message") or {}).get("content") or ""), state)
    next_state, response = process_turn(state, command, display_name)

    store.save_session(thread_id, next_state)
    store.save_processed_response(thread_id, message_key, response)
    return JSONResponse(response)

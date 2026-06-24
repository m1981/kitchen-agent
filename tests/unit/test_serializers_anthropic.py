"""
tests/test_serializers_anthropic.py
=====================================
Tests for serializer round-trip correctness with Anthropic provider history.

All provider-specific format detection has been removed.  The serializer
now treats all dict items as common format and passes them through,
ensuring every item has a ``turn_id``.

Covers
------
- dehydrate_history handles Anthropic plain-dict history without errors
- dehydrate_history round-trips Anthropic user text turn
- dehydrate_history round-trips Anthropic assistant text turn
- dehydrate_history round-trips Anthropic tool-use assistant turn
- dehydrate_history round-trips Anthropic tool-result user turn
- dehydrate_history + hydrate_history full round-trip (Anthropic)
- dehydrate_history + hydrate_history full round-trip (Gemini, unchanged)
- turn_ids are attached to Anthropic items just as for Gemini items
- Empty Anthropic history returns "[]"
- chat_service construction with orchestrator works
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai import types

from src.serializers import dehydrate_history, hydrate_history
from tests.helpers import FakeOrchestrator


# ---------------------------------------------------------------------------
# Helpers: canonical Anthropic history shapes (as built by AnthropicProvider)
# ---------------------------------------------------------------------------

def _anthropic_user_text(text: str) -> dict:
    return {"role": "user", "content": text}


def _anthropic_assistant_text(text: str) -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
    }


def _anthropic_assistant_tool_use(name: str, tool_input: dict, tool_id: str) -> dict:
    return {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input},
        ],
    }


def _anthropic_user_tool_result(tool_id: str, result_json: str) -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "content": result_json},
        ],
    }


# ---------------------------------------------------------------------------
# dehydrate_history — no crash on Anthropic dicts
# ---------------------------------------------------------------------------

def test_dehydrate_does_not_raise_for_anthropic_dict_history() -> None:
    """Plain dict history must not raise."""
    history = [
        _anthropic_user_text("Hello"),
        _anthropic_assistant_text("Hi there!"),
    ]
    result = dehydrate_history(history)
    assert isinstance(result, str)


def test_dehydrate_anthropic_produces_valid_json() -> None:
    history = [
        _anthropic_user_text("Hello"),
        _anthropic_assistant_text("Hi there!"),
    ]
    result = dehydrate_history(history)
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_dehydrate_anthropic_user_text_round_trip() -> None:
    """A plain-string user turn survives dehydrate → hydrate."""
    original = _anthropic_user_text("What hinges?")
    result = json.loads(dehydrate_history([original]))
    assert result[0]["role"] == "user"
    assert "What hinges?" in json.dumps(result[0])


def test_dehydrate_anthropic_assistant_text_round_trip() -> None:
    original = _anthropic_assistant_text("Use Blum hinges.")
    result = json.loads(dehydrate_history([original]))
    assert result[0]["role"] == "assistant"
    assert "Blum hinges" in json.dumps(result[0])


def test_dehydrate_anthropic_tool_use_turn() -> None:
    original = _anthropic_assistant_tool_use(
        "read_file", {"filepath": "data/test.md"}, "tid_1"
    )
    result = json.loads(dehydrate_history([original]))
    assert result[0]["role"] == "assistant"
    blob = json.dumps(result[0])
    assert "read_file" in blob
    assert "tid_1"    in blob


def test_dehydrate_anthropic_tool_result_turn() -> None:
    original = _anthropic_user_tool_result("tid_1", '{"content": "# Test"}')
    result = json.loads(dehydrate_history([original]))
    assert result[0]["role"] == "user"
    assert "tid_1" in json.dumps(result[0])


def test_dehydrate_anthropic_empty_history() -> None:
    assert dehydrate_history([]) == "[]"


# ---------------------------------------------------------------------------
# turn_ids attached to Anthropic items
# ---------------------------------------------------------------------------

def test_dehydrate_anthropic_attaches_turn_ids() -> None:
    history = [
        _anthropic_user_text("Hello"),
        _anthropic_assistant_text("Hi!"),
    ]
    result = json.loads(dehydrate_history(history, turn_ids=["uid-1", "aid-1"]))
    assert result[0]["turn_id"] == "uid-1"
    assert result[1]["turn_id"] == "aid-1"


def test_dehydrate_anthropic_generates_turn_id_when_omitted() -> None:
    """When no turn_ids provided, items get generated UUIDs."""
    history = [_anthropic_user_text("Hello")]
    result = json.loads(dehydrate_history(history))
    assert "turn_id" in result[0]
    assert len(result[0]["turn_id"]) == 36  # UUID format


# ---------------------------------------------------------------------------
# Full round-trip: dehydrate → hydrate (Anthropic)
# ---------------------------------------------------------------------------

def test_full_round_trip_anthropic_simple() -> None:
    """hydrate(dehydrate(history)) must reproduce equivalent plain dicts."""
    history = [
        _anthropic_user_text("Hello"),
        _anthropic_assistant_text("Hi there!"),
    ]
    json_str  = dehydrate_history(history)
    restored  = hydrate_history(json_str)

    assert len(restored) == 2
    assert isinstance(restored[0], dict)
    assert isinstance(restored[1], dict)
    assert restored[0]["role"] == "user"
    assert restored[1]["role"] == "assistant"


def test_full_round_trip_anthropic_tool_call_sequence() -> None:
    """Tool-use + tool-result pair round-trips correctly."""
    history = [
        _anthropic_user_text("Read test.md"),
        _anthropic_assistant_tool_use("read_file", {"filepath": "test.md"}, "c1"),
        _anthropic_user_tool_result("c1", '{"content": "hello"}'),
        _anthropic_assistant_text("The file says hello."),
    ]
    json_str = dehydrate_history(history)
    restored = hydrate_history(json_str)

    assert len(restored) == 4
    for item in restored:
        assert isinstance(item, dict)

    roles = [item["role"] for item in restored]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_full_round_trip_anthropic_with_turn_ids() -> None:
    """turn_ids survive the round-trip on Anthropic items."""
    history = [
        _anthropic_user_text("Hi"),
        _anthropic_assistant_text("Hello!"),
    ]
    ids      = ["u1", "a1"]
    json_str = dehydrate_history(history, turn_ids=ids)
    parsed   = json.loads(json_str)

    assert parsed[0]["turn_id"] == "u1"
    assert parsed[1]["turn_id"] == "a1"


# ---------------------------------------------------------------------------
# Gemini round-trip still works (regression guard)
# ---------------------------------------------------------------------------

def test_full_round_trip_gemini_text_unchanged() -> None:
    """Gemini Content objects still serialise and deserialise correctly."""
    history = [
        types.Content(role="user",  parts=[types.Part(text="Hello")]),
        types.Content(role="model", parts=[types.Part(text="Hi!")]),
    ]
    json_str = dehydrate_history(history)
    restored = hydrate_history(json_str)

    assert len(restored) == 2
    assert isinstance(restored[0], dict)
    assert isinstance(restored[1], dict)
    assert restored[0]["content"] == "Hello"
    assert restored[1]["content"] == "Hi!"


# ---------------------------------------------------------------------------
# chat_service integration
# ---------------------------------------------------------------------------

def test_chat_service_construction_with_orchestrator(tmp_path) -> None:
    """ChatService can be constructed with a TurnOrchestrator."""
    from src.repositories import SQLiteConnection, SQLiteSessionRepository
    from src.chat_service import ChatService

    db   = SQLiteConnection(db_path=str(tmp_path / "test.db"))
    repo = SQLiteSessionRepository(db)

    service = ChatService(repo, turn_orchestrator=FakeOrchestrator())
    assert service is not None

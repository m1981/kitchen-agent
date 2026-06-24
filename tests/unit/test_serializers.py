"""
tests/test_serializers.py
=========================
Unit tests for dehydrate_history / hydrate_history round-trip.

Covers:
 - Normal full cycle (text, function_call with signature, function_response)
 - Content with no parts is silently skipped
 - function_call without thought_signature
 - Unknown item type passes through
 - turn_id always present in output (generated when missing)
 - Gemini Content objects get turn_id from the object or a generated UUID
"""
import json

import pytest
from google.genai import types

from src.serializers import dehydrate_history, hydrate_history


# ---------------------------------------------------------------------------
# Full round-trip
# ---------------------------------------------------------------------------

def test_serialization_cycle() -> None:
    """
    Converts a complex Gemini history to JSON and back without losing data.
    Returns common format dicts with turn_id on every item.
    """
    original_history = [
        types.Content(role="user", parts=[types.Part(text="Read the file.")]),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="read_file", args={"filepath": "test.md"}, id="call_1"
                    ),
                    thought_signature=b"fake_encrypted_bytes_123",
                )
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="read_file", response={"content": "wood"}, id="call_1"
                    )
                )
            ],
        ),
    ]

    json_string = dehydrate_history(original_history)
    restored = hydrate_history(json_string)

    assert len(restored) == 3

    # Text part — common format
    assert restored[0]["role"] == "user"
    assert restored[0]["content"] == "Read the file."
    assert "turn_id" in restored[0]

    # Function call — common format with tool_calls
    assert restored[1]["role"] == "assistant"
    assert restored[1]["tool_calls"][0]["name"] == "read_file"
    assert restored[1]["tool_calls"][0]["id"] == "call_1"
    assert "turn_id" in restored[1]

    # Function response — common format
    assert restored[2]["role"] == "tool"
    assert restored[2]["tool_call_id"] == "call_1"
    assert "turn_id" in restored[2]
    # Response content is JSON-encoded string
    response = json.loads(restored[2]["content"])
    assert response == {"content": "wood"}


# ---------------------------------------------------------------------------
# Content with no parts is silently skipped
# ---------------------------------------------------------------------------

def test_dehydrate_skips_empty_parts() -> None:
    """A Content object with an empty parts list must be silently skipped."""
    history = [
        types.Content(role="user", parts=[types.Part(text="hello")]),
        types.Content(role="model", parts=[]),   # ← empty — must be skipped
    ]
    result = json.loads(dehydrate_history(history))
    assert len(result) == 1
    assert result[0]["content"] == "hello"


# ---------------------------------------------------------------------------
# function_call without thought_signature
# ---------------------------------------------------------------------------

def test_dehydrate_function_call_without_signature() -> None:
    """function_call with no thought_signature serialises correctly."""
    history = [
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="get_repo_map", args={}, id="call_2"
                    )
                    # no thought_signature
                )
            ],
        )
    ]
    data = json.loads(dehydrate_history(history))
    assert len(data) == 1
    item = data[0]
    # Common format
    assert item["role"] == "assistant"
    assert item["tool_calls"][0]["name"] == "get_repo_map"
    assert item["tool_calls"][0]["id"] == "call_2"
    assert "turn_id" in item


def test_hydrate_function_call_without_signature() -> None:
    """Hydrating a function_call in common format works correctly."""
    raw = json.dumps([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_2", "name": "get_repo_map", "arguments": {}}
            ],
            "turn_id": "tid-1",
        }
    ])
    restored = hydrate_history(raw)
    assert len(restored) == 1
    assert restored[0]["role"] == "assistant"
    assert restored[0]["tool_calls"][0]["name"] == "get_repo_map"


# ---------------------------------------------------------------------------
# Unknown item type passes through
# ---------------------------------------------------------------------------

def test_hydrate_passes_through_unknown_item_type() -> None:
    """An item with an unrecognised 'type' key passes through as-is."""
    raw = json.dumps([
        {"role": "user", "content": "good", "turn_id": "t1"},
        {"role": "user", "type": "alien_format", "payload": "???", "turn_id": "t2"},
    ])
    restored = hydrate_history(raw)
    assert len(restored) == 2
    assert restored[0]["content"] == "good"
    assert restored[1]["type"] == "alien_format"


# ---------------------------------------------------------------------------
# Edge cases for hydrate_history input
# ---------------------------------------------------------------------------

def test_hydrate_empty_string_returns_empty_list() -> None:
    assert hydrate_history("") == []


def test_hydrate_empty_json_array_returns_empty_list() -> None:
    assert hydrate_history("[]") == []


# ---------------------------------------------------------------------------
# Dehydrate: unrecognised Part type is skipped with a warning
# ---------------------------------------------------------------------------

def test_dehydrate_skips_unrecognised_part_type() -> None:
    """
    A Part that is neither text, function_call, nor function_response must be
    silently skipped.
    """
    binary_part = types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png")
    history = [
        types.Content(role="user", parts=[types.Part(text="before")]),
        types.Content(role="user", parts=[binary_part]),   # unrecognised
        types.Content(role="user", parts=[types.Part(text="after")]),
    ]
    result = json.loads(dehydrate_history(history))
    # Only the two text parts should be serialised; the binary part is dropped.
    assert len(result) == 2
    assert result[0]["content"] == "before"
    assert result[1]["content"] == "after"


# ---------------------------------------------------------------------------
# turn_id always present — generated when missing
# ---------------------------------------------------------------------------

def test_dehydrate_generates_turn_id_for_dict_items_without_one() -> None:
    """Dict items that lack turn_id get a generated UUID."""
    history = [{"role": "user", "content": "hello"}]
    result = json.loads(dehydrate_history(history))
    assert len(result) == 1
    assert "turn_id" in result[0]
    # Should be a valid UUID string
    assert len(result[0]["turn_id"]) == 36


def test_dehydrate_preserves_existing_turn_id_on_dict_items() -> None:
    """Dict items that already have turn_id keep it."""
    history = [{"role": "user", "content": "hello", "turn_id": "my-custom-id"}]
    result = json.loads(dehydrate_history(history))
    assert result[0]["turn_id"] == "my-custom-id"


def test_dehydrate_turn_ids_list_overrides_missing_turn_id() -> None:
    """When turn_ids list is provided, it is used for items without turn_id."""
    history = [{"role": "user", "content": "hello"}]
    result = json.loads(dehydrate_history(history, turn_ids=["explicit-id"]))
    assert result[0]["turn_id"] == "explicit-id"


def test_dehydrate_turn_ids_list_does_not_override_existing() -> None:
    """When an item already has turn_id, the turn_ids list does not override it."""
    history = [{"role": "user", "content": "hello", "turn_id": "existing"}]
    result = json.loads(dehydrate_history(history, turn_ids=["override"]))
    assert result[0]["turn_id"] == "existing"


def test_dehydrate_gemini_content_always_has_turn_id() -> None:
    """Gemini Content objects always get a turn_id in the output."""
    history = [types.Content(role="user", parts=[types.Part(text="hello")])]
    result = json.loads(dehydrate_history(history))
    assert "turn_id" in result[0]


def test_round_trip_preserves_turn_id() -> None:
    """turn_id survives dehydrate → hydrate round-trip."""
    history = [{"role": "user", "content": "hello", "turn_id": "stable-id"}]
    raw = dehydrate_history(history)
    restored = hydrate_history(raw)
    assert restored[0]["turn_id"] == "stable-id"


def test_dehydrate_dict_items_preserved_verbatim() -> None:
    """Dict items in common format are preserved with all fields."""
    history = [
        {"role": "user", "content": "hi", "turn_id": "u1"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "read_file", "arguments": {}}],
            "turn_id": "a1",
        },
    ]
    result = json.loads(dehydrate_history(history))
    assert len(result) == 2
    assert result[0]["turn_id"] == "u1"
    assert result[1]["tool_calls"][0]["id"] == "c1"
    assert result[1]["turn_id"] == "a1"

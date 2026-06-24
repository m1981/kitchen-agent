"""
tests/test_config.py
====================
Unit tests for the central Settings class (src/config.py).

Covers:
 - db_path and prompt_log_path computed properties (lines 35, 39)
 - parse_origins validator with a comma-separated string (line 53)
"""
from pathlib import Path

import pytest

from src.config import Settings


def test_db_path_derived_from_data_dir() -> None:
    """db_path must be data_dir / 'chats.db'."""
    s = Settings(data_dir=Path("my_data"))
    assert s.db_path == Path("my_data/chats.db")


def test_prompt_log_path_derived_from_data_dir() -> None:
    """prompt_log_path must be data_dir / 'prompt_log.md'."""
    s = Settings(data_dir=Path("my_data"))
    assert s.prompt_log_path == Path("my_data/prompt_log.md")


def test_parse_origins_from_comma_string() -> None:
    """ALLOWED_ORIGINS env var supplied as a comma-separated string is split correctly."""
    s = Settings(allowed_origins="http://localhost:5173,https://example.com")
    assert s.allowed_origins == ["http://localhost:5173", "https://example.com"]


def test_parse_origins_strips_whitespace() -> None:
    """Whitespace around entries in the comma-separated string is stripped."""
    s = Settings(allowed_origins=" http://a.test , http://b.test ")
    assert s.allowed_origins == ["http://a.test", "http://b.test"]


def test_parse_origins_filters_empty_segments() -> None:
    """Consecutive commas (empty segments) are ignored."""
    s = Settings(allowed_origins="http://a.test,,http://b.test")
    assert s.allowed_origins == ["http://a.test", "http://b.test"]


def test_parse_origins_list_passthrough() -> None:
    """When already a list, parse_origins returns it unchanged."""
    origins = ["http://localhost:5173"]
    s = Settings(allowed_origins=origins)
    assert s.allowed_origins == origins

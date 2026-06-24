"""
tests/test_config_provider.py
==============================
Tests for provider-related Settings fields added to config.py.

Covers:
  - Default provider is ``"gemini"``
  - ``llm_provider`` can be overridden via environment variable
  - ``anthropic_model`` has a sensible default
  - ``anthropic_api_key`` field exists and is nullable (str | None)
  - ``anthropic_temperature`` and ``anthropic_max_tokens`` have sensible defaults
"""
import os
import pytest

from src.config import Settings


def test_default_provider_is_gemini() -> None:
    s = Settings(_env_file=None)
    assert s.llm_provider == "gemini"


def test_llm_provider_can_be_set_to_anthropic() -> None:
    s = Settings(llm_provider="anthropic", _env_file=None)
    assert s.llm_provider == "anthropic"


def test_anthropic_model_has_default() -> None:
    s = Settings(_env_file=None)
    assert s.anthropic_model is not None
    assert len(s.anthropic_model) > 0
    # Should default to a recent Claude model
    assert "claude" in s.anthropic_model.lower()


def test_anthropic_model_can_be_overridden() -> None:
    s = Settings(anthropic_model="claude-3-opus-20240229", _env_file=None)
    assert s.anthropic_model == "claude-3-opus-20240229"


def test_anthropic_api_key_field_exists_and_is_nullable() -> None:
    """
    The anthropic_api_key field must be declared as ``str | None``.
    When explicitly set to None it must be stored as None.
    Environment values are accepted (present in CI/dev env) — that is correct
    behavior; this test validates the schema, not the runtime value.
    """
    s = Settings(anthropic_api_key=None, _env_file=None)
    assert s.anthropic_api_key is None

    s2 = Settings(anthropic_api_key="sk-ant-test-key", _env_file=None)
    assert s2.anthropic_api_key == "sk-ant-test-key"


def test_anthropic_api_key_accepts_env_var(monkeypatch) -> None:
    """ANTHROPIC_API_KEY from the shell environment must be picked up."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "sk-ant-from-env"


def test_anthropic_temperature_has_sensible_default() -> None:
    s = Settings(_env_file=None)
    assert 0.0 <= s.anthropic_temperature <= 2.0


def test_anthropic_temperature_can_be_overridden() -> None:
    s = Settings(anthropic_temperature=0.7, _env_file=None)
    assert s.anthropic_temperature == 0.7


def test_anthropic_max_tokens_has_positive_default() -> None:
    s = Settings(_env_file=None)
    assert s.anthropic_max_tokens > 0
    # Should be large enough for useful responses
    assert s.anthropic_max_tokens >= 1024

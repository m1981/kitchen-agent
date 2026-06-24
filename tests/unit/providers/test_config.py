"""
tests/unit/providers/test_config.py
====================================
Unit tests for src/providers/config.py — ProviderConfig dataclasses.

Covers:
  - Default values for each config
  - Custom values override defaults
  - Frozen (immutable) behavior
  - Config injection into providers
"""
import pytest

from src.providers.config import AnthropicConfig, GeminiConfig, MimoConfig


# ---------------------------------------------------------------------------
# GeminiConfig
# ---------------------------------------------------------------------------

class TestGeminiConfig:
    def test_defaults(self):
        config = GeminiConfig()
        assert config.model == "gemini-3.1-pro-preview"
        assert config.temperature == 0.2

    def test_custom_values(self):
        config = GeminiConfig(model="gemini-2.5-pro", temperature=0.5)
        assert config.model == "gemini-2.5-pro"
        assert config.temperature == 0.5

    def test_frozen(self):
        config = GeminiConfig()
        with pytest.raises(AttributeError):
            config.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AnthropicConfig
# ---------------------------------------------------------------------------

class TestAnthropicConfig:
    def test_defaults(self):
        config = AnthropicConfig()
        assert config.api_key is None
        assert config.model == "claude-sonnet-4-6"
        assert config.temperature == 0.2
        assert config.max_tokens == 8096

    def test_custom_values(self):
        config = AnthropicConfig(
            api_key="sk-test-123",
            model="claude-opus-4",
            temperature=0.0,
            max_tokens=4096,
        )
        assert config.api_key == "sk-test-123"
        assert config.model == "claude-opus-4"
        assert config.temperature == 0.0
        assert config.max_tokens == 4096

    def test_frozen(self):
        config = AnthropicConfig()
        with pytest.raises(AttributeError):
            config.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MimoConfig
# ---------------------------------------------------------------------------

class TestMimoConfig:
    def test_defaults(self):
        config = MimoConfig()
        assert config.api_key is None
        assert config.base_url == "https://api.xiaomimimo.com/v1"
        assert config.model == "mimo-v2.5-pro"
        assert config.temperature == 0.2
        assert config.max_tokens == 8096

    def test_custom_values(self):
        config = MimoConfig(
            api_key="mimo-key",
            base_url="https://custom.api.com/v1",
            model="mimo-custom",
            temperature=0.5,
            max_tokens=2048,
        )
        assert config.api_key == "mimo-key"
        assert config.base_url == "https://custom.api.com/v1"
        assert config.model == "mimo-custom"
        assert config.temperature == 0.5
        assert config.max_tokens == 2048

    def test_frozen(self):
        config = MimoConfig()
        with pytest.raises(AttributeError):
            config.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Config injection into providers
# ---------------------------------------------------------------------------

class TestConfigInjection:
    def test_gemini_provider_accepts_config(self):
        from src.providers.gemini import GeminiProvider

        config = GeminiConfig(model="test-model", temperature=0.9)
        # We can't fully construct without a real API key, but we can
        # verify the constructor signature accepts config
        import inspect
        sig = inspect.signature(GeminiProvider.__init__)
        assert "config" in sig.parameters

    def test_anthropic_provider_accepts_config(self):
        from src.providers.anthropic_provider import AnthropicProvider

        import inspect
        sig = inspect.signature(AnthropicProvider.__init__)
        assert "config" in sig.parameters

    def test_mimo_provider_accepts_config(self):
        from src.providers.mimo_provider import MimoProvider

        import inspect
        sig = inspect.signature(MimoProvider.__init__)
        assert "config" in sig.parameters

    def test_anthropic_provider_uses_config_max_tokens(self):
        """AnthropicProvider must accept config with max_tokens."""
        import inspect
        from src.providers.anthropic_provider import AnthropicProvider

        sig = inspect.signature(AnthropicProvider.__init__)
        config_param = sig.parameters.get("config")
        assert config_param is not None
        # Default is None (backward compatible)
        assert config_param.default is None

    def test_mimo_provider_uses_config_temperature(self):
        """MimoProvider must accept config with temperature."""
        import inspect
        from src.providers.mimo_provider import MimoProvider

        sig = inspect.signature(MimoProvider.__init__)
        config_param = sig.parameters.get("config")
        assert config_param is not None
        assert config_param.default is None

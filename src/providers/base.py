"""
src/providers/base.py
=====================
LLMProvider Protocol + provider registry factory.

Design
------
``LLMProvider`` is a ``runtime_checkable`` Protocol — any class that
implements ``complete``, ``complete_with_tools``, ``stream``, and
``stream_with_tools`` with the correct signatures satisfies it without
inheritance.  This lets us test structural compliance easily and avoids
coupling providers to a base class.

``get_provider()`` is the single entry point for the rest of the application.
It reads ``settings.llm_provider`` and returns the matching instance.  We
deliberately read settings at *call time* (not cached at module load) so that
runtime reconfiguration (e.g. in tests with ``monkeypatch`` or
``patch("src.config.settings")``) takes effect immediately.

Providers available:
  ``"gemini"``     → GeminiProvider   (default)
  ``"anthropic"``  → AnthropicProvider

Adding a new provider
---------------------
1. Create ``src/providers/my_provider.py`` implementing all 4 methods:
   ``complete``, ``complete_with_tools``, ``stream``, ``stream_with_tools``.
2. Add a new branch in ``get_provider()`` below.
3. Document the provider name in ``config.py``.
That is all — no other file needs to change.
"""
from __future__ import annotations

from typing import Protocol, Any, Iterator, runtime_checkable

from src.agent.context_assembler import AssembledContext
from src.agent.tool_executor import ToolCall, ToolResult


@runtime_checkable
class LLMProvider(Protocol):
    """
    Unified interface for all LLM providers.

    Providers receive an AssembledContext and return raw SDK responses.
    ResponseNormalizer converts raw responses to NormalizedResponse.

    Providers do NOT:
    - Execute tools (ToolExecutor owns that)
    - Manage conversation history (ContextAssembler owns that)
    - Select models dynamically (Settings/DI owns that)
    - Know about ToolRegistry (they receive final schemas only)

    All four methods are required:
    - ``complete`` / ``stream`` for plain turns
    - ``complete_with_tools`` / ``stream_with_tools`` for agentic tool loops
    """

    def complete(
        self,
        context: AssembledContext,
    ) -> Any:
        """Single turn completion. Returns raw provider SDK response."""
        ...

    def complete_with_tools(
        self,
        context: AssembledContext,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
    ) -> Any:
        """Completion after tool results are available."""
        ...

    def stream(
        self,
        context: AssembledContext,
    ) -> Iterator[Any]:
        """Stream a single turn. Yields raw SDK chunks."""
        ...

    def stream_with_tools(
        self,
        context: AssembledContext,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResult],
    ) -> Iterator[Any]:
        """Stream after tool results are available. Yields raw SDK chunks."""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_provider(
    provider_name: str | None = None,
    model_override: str | None = None,
) -> LLMProvider:
    """
    Return an LLM provider instance.

    Builds provider-specific config from ``Settings`` and injects it
    into the provider constructor.  Providers no longer read ``Settings``
    directly.

    Args:
        provider_name:  Which provider to use.  When ``None`` (the default) the
                        value is read from ``settings.llm_provider`` so the
                        server default applies.
        model_override: Model id to use instead of the provider's configured
                        default.  When ``None`` the provider reads its own
                        config field.

    Raises:
        ValueError: when the resolved provider name is not supported.
    """
    from src.config import settings

    name = (provider_name or settings.llm_provider or "gemini").lower()

    if name == "gemini":
        from src.providers.config import GeminiConfig
        from src.providers.gemini import GeminiProvider
        config = GeminiConfig(
            model=settings.gemini_model,
            temperature=settings.gemini_temperature,
        )
        return GeminiProvider(model_override=model_override, config=config)

    if name == "anthropic":
        from src.providers.config import AnthropicConfig
        from src.providers.anthropic_provider import AnthropicProvider
        config = AnthropicConfig(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            temperature=settings.anthropic_temperature,
            max_tokens=settings.anthropic_max_tokens,
        )
        return AnthropicProvider(model_override=model_override, config=config)

    if name == "mimo":
        from src.providers.config import MimoConfig
        from src.providers.mimo_provider import MimoProvider
        config = MimoConfig(
            api_key=settings.mimo_api_key,
            base_url=settings.mimo_base_url,
            model=settings.mimo_model,
            temperature=settings.mimo_temperature,
            max_tokens=settings.mimo_max_tokens,
        )
        return MimoProvider(model_override=model_override, config=config)

    raise ValueError(
        f"Unknown provider {name!r}. Valid: 'gemini', 'anthropic', 'mimo'"
    )

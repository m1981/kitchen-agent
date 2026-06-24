"""
Central test configuration.

Prevents the most common test isolation failures:
- lru_cache leaking between tests
- Real API keys bleeding into test runs
- Shared database state
"""
import pytest


# ── Cache clearing — prevents test pollution ──────────────────────

@pytest.fixture(autouse=True)
def clear_lru_caches():
    """
    Clear all lru_cache decorated functions between tests.
    Without this, singleton dependencies leak between tests.
    """
    yield
    # After each test, clear any known caches.
    # Add more as the codebase grows.
    try:
        from src.providers.base import get_provider
        get_provider.cache_clear() if hasattr(get_provider, 'cache_clear') else None
    except ImportError:
        pass


# ── Environment isolation ─────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """
    Prevent real API keys from leaking into tests.
    Every test that needs a key must set it explicitly.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


# ── Markers ───────────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m not slow')",
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests requiring real DB",
    )
    config.addinivalue_line(
        "markers",
        "migration: marks tests that will change during refactor",
    )

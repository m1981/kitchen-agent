"""
tests/unit/content/test_search_coordinator.py
===============================================
Unit tests for SearchCoordinator — fan-out search across backends.

The SearchCoordinator provides:
  - Fan-out to multiple search backends
  - Deduplication by content
  - Score-based ranking
  - Backend filtering

These tests use fakes — no real grep or file system access.
"""
import pytest

from src.content.search_coordinator import (
    GrepSearchBackend,
    SearchBackend,
    SearchCoordinator,
    SearchResult,
)


# ---------------------------------------------------------------------------
# Fakes for isolated testing
# ---------------------------------------------------------------------------

class FakeSearchBackend:
    """Controllable search backend for testing."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or []
        self.was_called = False
        self.last_query: str | None = None
        self.last_limit: int | None = None
        self.last_kwargs: dict = {}

    def search(
        self,
        query: str,
        limit: int,
        **kwargs,
    ) -> list[SearchResult]:
        self.was_called = True
        self.last_query = query
        self.last_limit = limit
        self.last_kwargs = kwargs
        return self._results[:limit]


# ---------------------------------------------------------------------------
# Tests: SearchCoordinator — fan-out
# ---------------------------------------------------------------------------

class TestFanOut:
    def test_calls_all_backends_when_no_filter(self):
        backend_a = FakeSearchBackend(results=[
            SearchResult(source="a", content="result A", score=0.9),
        ])
        backend_b = FakeSearchBackend(results=[
            SearchResult(source="b", content="result B", score=0.7),
        ])

        coordinator = SearchCoordinator(
            backends={"a": backend_a, "b": backend_b}
        )
        coordinator.search("test query", limit=10)

        assert backend_a.was_called
        assert backend_b.was_called

    def test_calls_only_filtered_backends(self):
        backend_a = FakeSearchBackend(results=[
            SearchResult(source="a", content="A result", score=0.9),
        ])
        backend_b = FakeSearchBackend(results=[
            SearchResult(source="b", content="B result", score=0.8),
        ])

        coordinator = SearchCoordinator(
            backends={"a": backend_a, "b": backend_b}
        )
        results = coordinator.search("query", limit=10, backends=["a"])

        assert backend_a.was_called
        assert not backend_b.was_called
        assert all(r.source == "a" for r in results)

    def test_empty_backends_returns_empty(self):
        coordinator = SearchCoordinator(backends={})
        results = coordinator.search("query", limit=10)
        assert results == []


# ---------------------------------------------------------------------------
# Tests: SearchCoordinator — ranking
# ---------------------------------------------------------------------------

class TestRanking:
    def test_results_sorted_by_score_descending(self):
        coordinator = SearchCoordinator(backends={
            "mixed": FakeSearchBackend(results=[
                SearchResult(source="x", content="low", score=0.3),
                SearchResult(source="x", content="high", score=0.9),
                SearchResult(source="x", content="mid", score=0.6),
            ])
        })

        results = coordinator.search("query", limit=10)

        assert results[0].content == "high"
        assert results[1].content == "mid"
        assert results[2].content == "low"

    def test_deduplicates_by_content(self):
        same_content = "duplicate result"
        backend_a = FakeSearchBackend(results=[
            SearchResult(source="a", content=same_content, score=0.9),
        ])
        backend_b = FakeSearchBackend(results=[
            SearchResult(source="b", content=same_content, score=0.8),
        ])

        coordinator = SearchCoordinator(
            backends={"a": backend_a, "b": backend_b}
        )
        results = coordinator.search("query", limit=10)

        contents = [r.content for r in results]
        assert len(contents) == len(set(contents)), "Duplicates found"
        assert len(results) == 1

    def test_respects_limit(self):
        coordinator = SearchCoordinator(backends={
            "many": FakeSearchBackend(results=[
                SearchResult(source="x", content=f"result {i}", score=float(i))
                for i in range(20)
            ])
        })

        results = coordinator.search("query", limit=5)

        assert len(results) == 5


# ---------------------------------------------------------------------------
# Tests: SearchCoordinator — query forwarding
# ---------------------------------------------------------------------------

class TestQueryForwarding:
    def test_query_forwarded_to_backend(self):
        backend = FakeSearchBackend()
        coordinator = SearchCoordinator(backends={"b": backend})

        coordinator.search("my query", limit=7)

        assert backend.last_query == "my query"
        assert backend.last_limit == 7

    def test_context_lines_forwarded_via_kwargs(self):
        """context_lines must be forwarded from coordinator to backend via **kwargs."""
        backend = FakeSearchBackend()
        coordinator = SearchCoordinator(backends={"b": backend})

        coordinator.search("query", limit=10, context_lines=5)

        assert backend.last_kwargs.get("context_lines") == 5


# ---------------------------------------------------------------------------
# Tests: SearchResult dataclass
# ---------------------------------------------------------------------------

class TestSearchResult:
    def test_fields(self):
        r = SearchResult(
            source="grep",
            content="matching line",
            score=1.0,
            metadata={"file": "test.md"},
        )
        assert r.source == "grep"
        assert r.content == "matching line"
        assert r.score == 1.0
        assert r.metadata == {"file": "test.md"}

    def test_default_metadata(self):
        r = SearchResult(source="test", content="c", score=0.5)
        assert r.metadata == {}


# ---------------------------------------------------------------------------
# Tests: SearchBackend protocol
# ---------------------------------------------------------------------------

class TestSearchBackendProtocol:
    def test_fake_satisfies_protocol(self):
        backend = FakeSearchBackend()
        # Structural check — has the right method
        assert hasattr(backend, "search")

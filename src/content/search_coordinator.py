"""
src/content/search_coordinator.py
===================================
SearchCoordinator — fan-out search across multiple backends.

Before this module, search was a single function in ``tools/file_ops.py``.
The SearchCoordinator provides:
  - A ``SearchBackend`` protocol that any backend can implement
  - Fan-out to multiple backends concurrently
  - Deduplication and score-based ranking
  - Backend filtering (caller can choose which backends to use)

Today: grep only (via GrepSearchBackend)
Tomorrow: BM25, embeddings — zero changes to callers
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A single search result from any backend."""

    source: str        # "grep" | "bm25" | "embedding"
    content: str
    score: float
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

class SearchBackend(Protocol):
    """
    Any search backend implements this protocol.
    Add BM25, embeddings, grep — all behind same interface.
    """

    def search(
        self,
        query: str,
        limit: int,
        **kwargs: Any,
    ) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class SearchCoordinator:
    """
    Fan-out search across multiple backends.
    Merge and rank results.
    Single place to tune search strategy.

    Today: grep only
    Tomorrow: BM25 + embeddings, no changes to callers
    """

    def __init__(self, backends: dict[str, SearchBackend]) -> None:
        self._backends = backends

    def search(
        self,
        query: str,
        limit: int = 10,
        backends: list[str] | None = None,
        **kwargs: Any,
    ) -> list[SearchResult]:
        """
        Search across all (or selected) backends and return ranked results.

        Args:
            query:    Search query string.
            limit:    Maximum number of results to return.
            backends: Optional list of backend names to use.
                      None = use all available backends.
            **kwargs: Extra parameters forwarded to each backend
                      (e.g. context_lines for grep).

        Returns:
            Deduplicated, score-ranked list of SearchResult.
        """
        active = {
            name: backend
            for name, backend in self._backends.items()
            if backends is None or name in backends
        }

        all_results: list[SearchResult] = []
        for backend in active.values():
            results = backend.search(query, limit, **kwargs)
            all_results.extend(results)

        return self._rank(all_results, limit)

    def _rank(
        self,
        results: list[SearchResult],
        limit: int,
    ) -> list[SearchResult]:
        """
        Deduplicate by content and sort by score (descending).

        Simple score-based ranking today.
        Replace with RRF (Reciprocal Rank Fusion) when
        multiple backends are active.
        """
        seen_content: set[str] = set()
        unique: list[SearchResult] = []
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            if r.content not in seen_content:
                seen_content.add(r.content)
                unique.append(r)
        return unique[:limit]


# ---------------------------------------------------------------------------
# Concrete backends
# ---------------------------------------------------------------------------

class GrepSearchBackend:
    """
    Grep-based search backend — wraps the existing search_knowledge_base.

    This is the current implementation, now behind the SearchBackend protocol.
    """

    def __init__(self, base_dir: str = "data") -> None:
        self._base_dir = base_dir

    def search(
        self,
        query: str,
        limit: int,
        **kwargs: Any,
    ) -> list[SearchResult]:
        from src.tools.file_ops import search_knowledge_base

        result = search_knowledge_base(
            query, base_dir=self._base_dir, context_lines=kwargs.get("context_lines", 2),
        )

        if "error" in result:
            return []

        content = result.get("content", "")
        if not content or content.startswith("No matches found"):
            return []

        # Split into file blocks and return as results
        results: list[SearchResult] = []
        for block in content.split("\n\n=== "):
            if not block.strip():
                continue
            # Re-add prefix if stripped
            if not block.startswith("=== "):
                block = "=== " + block
            results.append(SearchResult(
                source="grep",
                content=block,
                score=1.0,  # grep has no score, flat ranking
                metadata={"raw_block": block},
            ))
            if len(results) >= limit:
                break

        return results

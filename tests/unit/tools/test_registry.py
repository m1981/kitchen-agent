"""
tests/test_registry.py
======================
Unit tests for src/tools/registry.py.

Covers:
  - Every registry entry has a non-empty name and description.
  - ToolRegistry handler lookup matches entry callables.
  - ToolRegistry schemas match entries in order and length.
  - Required fields are declared on each parametrised tool.
  - Zero-argument tools (get_repo_map, search_knowledge_base wrappers) have
    required=[] (not omitted).
  - base_dir is NOT a parameter on get_repo_map or search_knowledge_base
    (path-traversal guard).
  - Callable wrappers for get_repo_map and search_knowledge_base actually
    invoke the underlying functions with the correct fixed base_dir.
"""
from unittest.mock import patch

import pytest
from google.genai import types

from src.tools.registry import (
    ToolCategory,
    ToolEntry,
    ToolRegistry,
    build_default_registry,
)


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

def test_tools_is_nonempty() -> None:
    registry = build_default_registry()
    assert len(registry.tool_names) > 0


def test_every_entry_is_tool_entry() -> None:
    registry = build_default_registry()
    for entry in registry.get_all_entries():
        assert isinstance(entry, ToolEntry)


def test_every_declaration_has_name_and_description() -> None:
    registry = build_default_registry()
    for entry in registry.get_all_entries():
        d = entry.declaration
        assert d.name, f"Empty name on {d}"
        assert d.description, f"Empty description for tool '{d.name}'"


def test_every_entry_has_callable() -> None:
    registry = build_default_registry()
    for entry in registry.get_all_entries():
        assert callable(entry.fn), f"fn for '{entry.declaration.name}' is not callable"


# ---------------------------------------------------------------------------
# ToolRegistry handler lookup
# ---------------------------------------------------------------------------

def test_handler_keys_match_tool_names() -> None:
    registry = build_default_registry()
    for name in registry.tool_names:
        handler = registry.get_handler(name)
        assert callable(handler)


def test_handler_matches_entry_fns() -> None:
    registry = build_default_registry()
    for entry in registry.get_all_entries():
        assert registry.get_handler(entry.declaration.name) is entry.fn


# ---------------------------------------------------------------------------
# ToolRegistry schemas
# ---------------------------------------------------------------------------

def test_schemas_length_matches_entries() -> None:
    registry = build_default_registry()
    schemas = registry.schemas_for_provider("gemini")
    assert len(schemas) == len(registry.get_all_entries())


def test_schemas_order_matches_entries() -> None:
    registry = build_default_registry()
    schemas = registry.schemas_for_provider("gemini")
    for schema, entry in zip(schemas, registry.get_all_entries()):
        assert schema is entry.declaration


def test_schemas_are_function_declaration_instances() -> None:
    registry = build_default_registry()
    for schema in registry.schemas_for_provider("gemini"):
        assert isinstance(schema, types.FunctionDeclaration)


# ---------------------------------------------------------------------------
# Per-tool schema correctness
# ---------------------------------------------------------------------------

def _declaration(name: str) -> types.FunctionDeclaration:
    """Helper: retrieve a declaration by tool name."""
    registry = build_default_registry()
    for entry in registry.get_all_entries():
        if entry.declaration.name == name:
            return entry.declaration
    raise KeyError(f"No tool named '{name}'")


@pytest.mark.parametrize("tool_name,required_fields", [
    ("read_file",             ["filepath"]),
    ("edit_file",             ["filepath", "search_text", "replace_text"]),
    ("create_file",           ["filepath", "content"]),
    ("search_knowledge_base", ["query"]),
])
def test_required_fields_declared(tool_name: str, required_fields: list[str]) -> None:
    decl = _declaration(tool_name)
    schema_required = list(decl.parameters.required or [])
    for field in required_fields:
        assert field in schema_required, (
            f"'{field}' not in required for tool '{tool_name}'"
        )


@pytest.mark.parametrize("tool_name", ["get_repo_map", "search_knowledge_base"])
def test_zero_or_single_arg_tools_have_explicit_required(tool_name: str) -> None:
    """required must be present (even if empty) — not None/omitted."""
    decl = _declaration(tool_name)
    assert decl.parameters.required is not None, (
        f"tool '{tool_name}' has required=None; should be an explicit list"
    )


# ---------------------------------------------------------------------------
# base_dir is NOT exposed on get_repo_map or search_knowledge_base
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool_name", ["get_repo_map", "search_knowledge_base"])
def test_base_dir_not_in_schema(tool_name: str) -> None:
    """base_dir must never be a declared parameter (path-traversal guard)."""
    decl = _declaration(tool_name)
    props = decl.parameters.properties or {}
    assert "base_dir" not in props, (
        f"'base_dir' must not be exposed in schema for tool '{tool_name}'"
    )


# ---------------------------------------------------------------------------
# Wrapper callables invoke underlying functions with fixed base_dir
# ---------------------------------------------------------------------------

def test_get_repo_map_wrapper_passes_data_dir(tmp_path) -> None:
    """The get_repo_map fn wrapper must pass settings.data_dir as base_dir."""
    captured: dict = {}

    def fake_get_repo_map(base_dir: str = "data") -> dict:
        captured["base_dir"] = base_dir
        return {"content": "ok"}

    # Patch the names the lambda closes over, then call the entry fn directly
    # while the patches are still active.  No module reload needed.
    with (
        patch("src.tools.registry.get_repo_map", fake_get_repo_map),
        patch("src.tools.registry.settings.data_dir", tmp_path),
    ):
        from src.tools.registry import _get_repo_map_entry
        _get_repo_map_entry.fn()

    assert "base_dir" in captured
    assert captured["base_dir"] == str(tmp_path)


def test_search_knowledge_base_wrapper_passes_data_dir(tmp_path) -> None:
    """The search_knowledge_base fn wrapper must pass settings.data_dir as base_dir."""
    captured: dict = {}

    def fake_search(query: str, base_dir: str = "data", context_lines: int = 2) -> dict:
        captured["base_dir"] = base_dir
        captured["query"] = query
        return {"content": "ok"}

    with (
        patch("src.tools.registry.search_knowledge_base", fake_search),
        patch("src.tools.registry.settings.data_dir", tmp_path),
    ):
        from src.tools.registry import _search_knowledge_base_entry
        _search_knowledge_base_entry.fn(query="blum")

    assert captured["base_dir"] == str(tmp_path)
    assert captured["query"] == "blum"


def test_build_default_registry_accepts_search_coordinator() -> None:
    """build_default_registry must accept an optional SearchCoordinator."""
    from src.content.search_coordinator import SearchCoordinator

    coordinator = SearchCoordinator(backends={})
    registry = build_default_registry(search_coordinator=coordinator)
    assert isinstance(registry, ToolRegistry)
    assert "search_knowledge_base" in registry.tool_names


def test_search_tool_uses_coordinator_when_provided(tmp_path) -> None:
    """When a SearchCoordinator is provided, the search tool must use it."""
    from src.content.search_coordinator import SearchCoordinator, SearchResult

    class SpyBackend:
        def __init__(self):
            self.was_called = False
            self.last_kwargs: dict = {}

        def search(self, query: str, limit: int, **kwargs) -> list[SearchResult]:
            self.was_called = True
            self.last_kwargs = kwargs
            return [SearchResult(source="spy", content=f"result for {query}", score=1.0)]

    spy = SpyBackend()
    coordinator = SearchCoordinator(backends={"spy": spy})
    registry = build_default_registry(search_coordinator=coordinator)

    handler = registry.get_handler("search_knowledge_base")
    result = handler(query="blum", context_lines=3)

    assert spy.was_called, "SearchCoordinator backend was not called"
    assert spy.last_kwargs.get("context_lines") == 3
    assert "error" not in result
    assert "result for blum" in result["content"]


def test_search_tool_forwards_context_lines_to_coordinator(tmp_path) -> None:
    """context_lines must be forwarded from tool handler through coordinator to backend."""
    from src.content.search_coordinator import SearchCoordinator, SearchResult

    class SpyBackend:
        def __init__(self):
            self.last_kwargs: dict = {}

        def search(self, query: str, limit: int, **kwargs) -> list[SearchResult]:
            self.last_kwargs = kwargs
            return [SearchResult(source="spy", content="found", score=1.0)]

    spy = SpyBackend()
    coordinator = SearchCoordinator(backends={"spy": spy})
    registry = build_default_registry(search_coordinator=coordinator)

    handler = registry.get_handler("search_knowledge_base")
    handler(query="test", context_lines=5)

    assert spy.last_kwargs.get("context_lines") == 5


# ---------------------------------------------------------------------------
# ToolCategory enum
# ---------------------------------------------------------------------------

class TestToolCategory:
    def test_all_expected_categories_exist(self):
        expected = {"DISCOVERY", "FILE_OPERATIONS", "SEARCH", "NOTES", "WEB"}
        actual = {cat.name for cat in ToolCategory}
        assert actual == expected

    def test_categories_are_unique(self):
        values = [cat.value for cat in ToolCategory]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# ToolEntry — category field
# ---------------------------------------------------------------------------

class TestToolEntryCategory:
    def test_default_category_is_file_operations(self):
        """Entries without explicit category default to FILE_OPERATIONS."""
        from google.genai import types
        entry = ToolEntry(
            declaration=types.FunctionDeclaration(
                name="test_tool",
                description="Test",
                parameters=types.Schema(type=types.Type.OBJECT),
            ),
            fn=lambda: {},
        )
        assert entry.category == ToolCategory.FILE_OPERATIONS

    def test_explicit_category_preserved(self):
        from google.genai import types
        entry = ToolEntry(
            declaration=types.FunctionDeclaration(
                name="test_tool",
                description="Test",
                parameters=types.Schema(type=types.Type.OBJECT),
            ),
            fn=lambda: {},
            category=ToolCategory.SEARCH,
        )
        assert entry.category == ToolCategory.SEARCH


# ---------------------------------------------------------------------------
# Existing tool entries — category assignments
# ---------------------------------------------------------------------------

class TestExistingToolCategories:
    def test_get_repo_map_is_discovery(self):
        registry = build_default_registry()
        entry = next(e for e in registry.get_all_entries() if e.declaration.name == "get_repo_map")
        assert entry.category == ToolCategory.DISCOVERY

    def test_search_knowledge_base_is_search(self):
        registry = build_default_registry()
        entry = next(e for e in registry.get_all_entries() if e.declaration.name == "search_knowledge_base")
        assert entry.category == ToolCategory.SEARCH

    def test_read_file_is_file_operations(self):
        registry = build_default_registry()
        entry = next(e for e in registry.get_all_entries() if e.declaration.name == "read_file")
        assert entry.category == ToolCategory.FILE_OPERATIONS

    def test_edit_file_is_file_operations(self):
        registry = build_default_registry()
        entry = next(e for e in registry.get_all_entries() if e.declaration.name == "edit_file")
        assert entry.category == ToolCategory.FILE_OPERATIONS

    def test_create_file_is_file_operations(self):
        registry = build_default_registry()
        entry = next(e for e in registry.get_all_entries() if e.declaration.name == "create_file")
        assert entry.category == ToolCategory.FILE_OPERATIONS


# ---------------------------------------------------------------------------
# ToolRegistry — category filtering
# ---------------------------------------------------------------------------

class TestRegistryCategoryFiltering:
    def test_schemas_for_provider_returns_all_when_no_filter(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider("gemini")
        assert len(schemas) == len(registry.get_all_entries())

    def test_schemas_for_provider_filters_by_category(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider(
            "gemini",
            categories=[ToolCategory.SEARCH],
        )
        names = [s.name for s in schemas]
        assert "search_knowledge_base" in names
        assert "read_file" not in names
        assert "get_repo_map" not in names

    def test_filter_discovery_only(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider(
            "gemini",
            categories=[ToolCategory.DISCOVERY],
        )
        names = [s.name for s in schemas]
        assert "get_repo_map" in names
        assert len(schemas) == 1

    def test_filter_file_operations(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider(
            "gemini",
            categories=[ToolCategory.FILE_OPERATIONS],
        )
        names = [s.name for s in schemas]
        assert "read_file" in names
        assert "edit_file" in names
        assert "create_file" in names
        assert "get_repo_map" not in names
        assert "search_knowledge_base" not in names

    def test_filter_multiple_categories(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider(
            "gemini",
            categories=[ToolCategory.DISCOVERY, ToolCategory.SEARCH],
        )
        names = [s.name for s in schemas]
        assert "get_repo_map" in names
        assert "search_knowledge_base" in names
        assert "read_file" not in names

    def test_filter_empty_category_returns_empty(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider(
            "gemini",
            categories=[ToolCategory.NOTES],  # no tools in this category yet
        )
        assert schemas == []


# ---------------------------------------------------------------------------
# ToolRegistry — get_entries_by_category
# ---------------------------------------------------------------------------

class TestGetEntriesByCategory:
    def test_returns_entries_matching_category(self):
        registry = build_default_registry()
        entries = registry.get_entries_by_category([ToolCategory.SEARCH])
        assert len(entries) == 1
        assert entries[0].declaration.name == "search_knowledge_base"

    def test_returns_empty_for_unused_category(self):
        registry = build_default_registry()
        entries = registry.get_entries_by_category([ToolCategory.NOTES])
        assert entries == []


# ---------------------------------------------------------------------------
# ToolRegistry — get_handler still works
# ---------------------------------------------------------------------------

class TestRegistryGetHandler:
    def test_get_handler_returns_callable(self):
        registry = build_default_registry()
        handler = registry.get_handler("read_file")
        assert callable(handler)

    def test_get_handler_unknown_tool_raises(self):
        registry = build_default_registry()
        with pytest.raises(ValueError, match="Unknown tool: 'ghost_tool'"):
            registry.get_handler("ghost_tool")



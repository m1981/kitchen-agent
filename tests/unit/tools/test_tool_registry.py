"""
tests/unit/tools/test_tool_registry.py
========================================
Unit tests for the ToolRegistry class in src/tools/registry.py.

The ToolRegistry is the class-based interface for tool management.
It supports handler lookup, schema generation per provider, and
tool discovery.
"""
import pytest
from google.genai import types

from src.tools.registry import (
    ToolCategory,
    ToolEntry,
    ToolRegistry,
    build_default_registry,
)


# ---------------------------------------------------------------------------
# ToolRegistry — handler lookup
# ---------------------------------------------------------------------------

class TestGetHandler:
    def test_returns_callable_for_known_tool(self):
        registry = build_default_registry()
        handler = registry.get_handler("read_file")
        assert callable(handler)

    def test_raises_for_unknown_tool(self):
        registry = build_default_registry()
        with pytest.raises(ValueError, match="Unknown tool"):
            registry.get_handler("nonexistent_tool")

    def test_handler_matches_entry_fn(self):
        """ToolRegistry.get_handler must return the same callable as the entry's fn."""
        registry = build_default_registry()
        for entry in registry.get_all_entries():
            assert registry.get_handler(entry.declaration.name) is entry.fn


# ---------------------------------------------------------------------------
# ToolRegistry — schema generation
# ---------------------------------------------------------------------------

class TestSchemasForProvider:
    def test_gemini_returns_function_declarations(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider("gemini")
        assert len(schemas) == len(registry.get_all_entries())
        for schema in schemas:
            assert isinstance(schema, types.FunctionDeclaration)

    def test_anthropic_returns_tool_param_dicts(self):
        registry = build_default_registry()
        schemas = registry.schemas_for_provider("anthropic")
        assert len(schemas) == len(registry.get_all_entries())
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert "parameters" not in schema  # Anthropic uses input_schema

    def test_unknown_provider_raises(self):
        registry = build_default_registry()
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.schemas_for_provider("openai")


# ---------------------------------------------------------------------------
# ToolRegistry — tool discovery
# ---------------------------------------------------------------------------

class TestToolDiscovery:
    def test_tool_names_match_entry_names(self):
        registry = build_default_registry()
        expected = [e.declaration.name for e in registry.get_all_entries()]
        assert registry.tool_names == expected

    def test_tool_names_ordered(self):
        registry = build_default_registry()
        expected = ["get_repo_map", "search_knowledge_base", "read_file", "edit_file", "create_file"]
        assert registry.tool_names == expected

    def test_get_all_entries_returns_tool_entries(self):
        registry = build_default_registry()
        entries = registry.get_all_entries()
        assert all(isinstance(e, ToolEntry) for e in entries)
        assert len(entries) == 5


# ---------------------------------------------------------------------------
# ToolRegistry — registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_adds_tool(self):
        registry = ToolRegistry()
        assert len(registry.tool_names) == 0

        entry = ToolEntry(
            declaration=types.FunctionDeclaration(
                name="test_tool",
                description="A test tool.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            fn=lambda: {"ok": True},
        )
        registry.register(entry)
        assert "test_tool" in registry.tool_names
        handler = registry.get_handler("test_tool")
        assert handler() == {"ok": True}


# ---------------------------------------------------------------------------
# build_default_registry
# ---------------------------------------------------------------------------

class TestBuildDefaultRegistry:
    def test_returns_tool_registry_instance(self):
        registry = build_default_registry()
        assert isinstance(registry, ToolRegistry)

    def test_has_all_five_tools(self):
        registry = build_default_registry()
        assert len(registry.tool_names) == 5

    def test_schemas_match_entries(self):
        """The class-based API must produce schemas matching the entries."""
        registry = build_default_registry()
        class_schemas = registry.schemas_for_provider("gemini")
        entries = registry.get_all_entries()
        assert len(class_schemas) == len(entries)
        for cs, entry in zip(class_schemas, entries):
            assert cs is entry.declaration  # same objects


# ---------------------------------------------------------------------------
# ToolCategory enum
# ---------------------------------------------------------------------------

class TestToolCategory:
    def test_enum_values_exist(self):
        assert ToolCategory.DISCOVERY is not None
        assert ToolCategory.FILE_OPERATIONS is not None
        assert ToolCategory.SEARCH is not None

    def test_enum_values_are_unique(self):
        values = [c.value for c in ToolCategory]
        assert len(values) == len(set(values))

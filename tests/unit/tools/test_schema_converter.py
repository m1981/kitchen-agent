"""
tests/unit/tools/test_schema_converter.py
==========================================
Unit tests for src/tools/schema_converter.py — ToolSchemaConverter.

Covers:
  - to_gemini() returns declaration unchanged
  - to_anthropic() produces correct ToolParam dict
  - to_openai_compat() produces correct function-calling dict
  - _schema_to_dict() handles all Gemini Schema types
  - Round-trip: same declaration produces equivalent tool semantics for all providers
"""
import pytest
from google.genai import types

from src.tools.schema_converter import ToolSchemaConverter


# ---------------------------------------------------------------------------
# Fixtures — reusable FunctionDeclaration objects
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_declaration() -> types.FunctionDeclaration:
    """Tool with one required string parameter."""
    return types.FunctionDeclaration(
        name="read_file",
        description="Read a file from disk.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "filepath": types.Schema(
                    type=types.Type.STRING,
                    description="Path to the file.",
                ),
            },
            required=["filepath"],
        ),
    )


@pytest.fixture
def complex_declaration() -> types.FunctionDeclaration:
    """Tool with multiple parameter types and optional fields."""
    return types.FunctionDeclaration(
        name="edit_file",
        description="Edit a file using search and replace.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "filepath": types.Schema(type=types.Type.STRING, description="File path."),
                "search_text": types.Schema(type=types.Type.STRING, description="Text to find."),
                "replace_text": types.Schema(type=types.Type.STRING, description="Replacement text."),
                "backup": types.Schema(type=types.Type.BOOLEAN, description="Create backup."),
                "max_lines": types.Schema(type=types.Type.INTEGER, description="Max lines to scan."),
            },
            required=["filepath", "search_text", "replace_text"],
        ),
    )


@pytest.fixture
def no_params_declaration() -> types.FunctionDeclaration:
    """Tool with no parameters."""
    return types.FunctionDeclaration(
        name="get_repo_map",
        description="Get a map of the repository.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={},
            required=[],
        ),
    )


@pytest.fixture
def nested_object_declaration() -> types.FunctionDeclaration:
    """Tool with a nested object parameter."""
    return types.FunctionDeclaration(
        name="create_note",
        description="Create a note.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "note": types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "title": types.Schema(type=types.Type.STRING),
                        "body": types.Schema(type=types.Type.STRING),
                    },
                    required=["title"],
                ),
            },
            required=["note"],
        ),
    )


# ---------------------------------------------------------------------------
# to_gemini — passthrough
# ---------------------------------------------------------------------------

class TestToGemini:
    def test_returns_declaration_unchanged(self, simple_declaration):
        result = ToolSchemaConverter.to_gemini(simple_declaration)
        assert result is simple_declaration

    def test_identity_preserves_all_fields(self, complex_declaration):
        result = ToolSchemaConverter.to_gemini(complex_declaration)
        assert result.name == "edit_file"
        assert result.description == "Edit a file using search and replace."
        assert "filepath" in result.parameters.properties


# ---------------------------------------------------------------------------
# to_anthropic — ToolParam format
# ---------------------------------------------------------------------------

class TestToAnthropic:
    def test_basic_structure(self, simple_declaration):
        result = ToolSchemaConverter.to_anthropic(simple_declaration)

        assert result["name"] == "read_file"
        assert result["description"] == "Read a file from disk."
        assert "input_schema" in result
        assert result["input_schema"]["type"] == "object"

    def test_properties_converted(self, simple_declaration):
        result = ToolSchemaConverter.to_anthropic(simple_declaration)
        props = result["input_schema"]["properties"]

        assert "filepath" in props
        assert props["filepath"]["type"] == "string"
        assert props["filepath"]["description"] == "Path to the file."

    def test_required_fields_preserved(self, simple_declaration):
        result = ToolSchemaConverter.to_anthropic(simple_declaration)
        assert result["input_schema"]["required"] == ["filepath"]

    def test_multiple_required_fields(self, complex_declaration):
        result = ToolSchemaConverter.to_anthropic(complex_declaration)
        required = result["input_schema"]["required"]

        assert "filepath" in required
        assert "search_text" in required
        assert "replace_text" in required

    def test_optional_fields_not_in_required(self, complex_declaration):
        result = ToolSchemaConverter.to_anthropic(complex_declaration)
        required = result["input_schema"]["required"]

        assert "backup" not in required
        assert "max_lines" not in required

    def test_boolean_type(self, complex_declaration):
        result = ToolSchemaConverter.to_anthropic(complex_declaration)
        assert result["input_schema"]["properties"]["backup"]["type"] == "boolean"

    def test_integer_type(self, complex_declaration):
        result = ToolSchemaConverter.to_anthropic(complex_declaration)
        assert result["input_schema"]["properties"]["max_lines"]["type"] == "integer"

    def test_no_params_has_empty_properties(self, no_params_declaration):
        result = ToolSchemaConverter.to_anthropic(no_params_declaration)
        assert result["input_schema"]["properties"] == {}
        assert result["input_schema"]["type"] == "object"

    def test_nested_object(self, nested_object_declaration):
        result = ToolSchemaConverter.to_anthropic(nested_object_declaration)
        note_prop = result["input_schema"]["properties"]["note"]

        assert note_prop["type"] == "object"
        assert "title" in note_prop["properties"]
        assert "body" in note_prop["properties"]
        assert note_prop["required"] == ["title"]

    def test_empty_description_becomes_empty_string(self):
        decl = types.FunctionDeclaration(
            name="test",
            description="",
            parameters=types.Schema(type=types.Type.OBJECT),
        )
        result = ToolSchemaConverter.to_anthropic(decl)
        assert result["description"] == ""


# ---------------------------------------------------------------------------
# to_openai_compat — function-calling format
# ---------------------------------------------------------------------------

class TestToOpenAICompat:
    def test_basic_structure(self, simple_declaration):
        result = ToolSchemaConverter.to_openai_compat(simple_declaration)

        assert result["type"] == "function"
        assert "function" in result
        assert result["function"]["name"] == "read_file"
        assert result["function"]["description"] == "Read a file from disk."

    def test_parameters_converted(self, simple_declaration):
        result = ToolSchemaConverter.to_openai_compat(simple_declaration)
        params = result["function"]["parameters"]

        assert params["type"] == "object"
        assert "filepath" in params["properties"]
        assert params["properties"]["filepath"]["type"] == "string"

    def test_required_preserved(self, simple_declaration):
        result = ToolSchemaConverter.to_openai_compat(simple_declaration)
        assert result["function"]["parameters"]["required"] == ["filepath"]

    def test_multiple_types(self, complex_declaration):
        result = ToolSchemaConverter.to_openai_compat(complex_declaration)
        props = result["function"]["parameters"]["properties"]

        assert props["filepath"]["type"] == "string"
        assert props["backup"]["type"] == "boolean"
        assert props["max_lines"]["type"] == "integer"

    def test_no_params_has_empty_properties(self, no_params_declaration):
        result = ToolSchemaConverter.to_openai_compat(no_params_declaration)
        params = result["function"]["parameters"]

        assert params["type"] == "object"
        assert params["properties"] == {}

    def test_nested_object(self, nested_object_declaration):
        result = ToolSchemaConverter.to_openai_compat(nested_object_declaration)
        note_prop = result["function"]["parameters"]["properties"]["note"]

        assert note_prop["type"] == "object"
        assert "title" in note_prop["properties"]


# ---------------------------------------------------------------------------
# _schema_to_dict — edge cases
# ---------------------------------------------------------------------------

class TestSchemaToDict:
    def test_none_schema_returns_object(self):
        result = ToolSchemaConverter._schema_to_dict(None)
        assert result == {"type": "object", "properties": {}}

    def test_string_type(self):
        schema = types.Schema(type=types.Type.STRING)
        result = ToolSchemaConverter._schema_to_dict(schema)
        assert result["type"] == "string"

    def test_number_type(self):
        schema = types.Schema(type=types.Type.NUMBER)
        result = ToolSchemaConverter._schema_to_dict(schema)
        assert result["type"] == "number"

    def test_array_type(self):
        schema = types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
        )
        result = ToolSchemaConverter._schema_to_dict(schema)
        assert result["type"] == "array"

    def test_description_preserved(self):
        schema = types.Schema(type=types.Type.STRING, description="A name.")
        result = ToolSchemaConverter._schema_to_dict(schema)
        assert result["description"] == "A name."

    def test_no_description_omitted(self):
        schema = types.Schema(type=types.Type.STRING)
        result = ToolSchemaConverter._schema_to_dict(schema)
        assert "description" not in result


# ---------------------------------------------------------------------------
# Cross-provider semantic equivalence
# ---------------------------------------------------------------------------

class TestCrossProviderEquivalence:
    """Same declaration must expose the same tool name and parameter names
    regardless of which provider format is used."""

    def test_tool_name_matches(self, simple_declaration):
        gemini = ToolSchemaConverter.to_gemini(simple_declaration)
        anthropic = ToolSchemaConverter.to_anthropic(simple_declaration)
        openai = ToolSchemaConverter.to_openai_compat(simple_declaration)

        assert gemini.name == anthropic["name"] == openai["function"]["name"]

    def test_description_matches(self, simple_declaration):
        gemini = ToolSchemaConverter.to_gemini(simple_declaration)
        anthropic = ToolSchemaConverter.to_anthropic(simple_declaration)
        openai = ToolSchemaConverter.to_openai_compat(simple_declaration)

        assert gemini.description == anthropic["description"] == openai["function"]["description"]

    def test_parameter_names_match(self, complex_declaration):
        gemini = ToolSchemaConverter.to_gemini(complex_declaration)
        anthropic = ToolSchemaConverter.to_anthropic(complex_declaration)
        openai = ToolSchemaConverter.to_openai_compat(complex_declaration)

        gemini_params = set(gemini.parameters.properties.keys())
        anthropic_params = set(anthropic["input_schema"]["properties"].keys())
        openai_params = set(openai["function"]["parameters"]["properties"].keys())

        assert gemini_params == anthropic_params == openai_params

    def test_required_fields_match(self, complex_declaration):
        gemini = ToolSchemaConverter.to_gemini(complex_declaration)
        anthropic = ToolSchemaConverter.to_anthropic(complex_declaration)
        openai = ToolSchemaConverter.to_openai_compat(complex_declaration)

        gemini_required = set(gemini.parameters.required or [])
        anthropic_required = set(anthropic["input_schema"].get("required", []))
        openai_required = set(openai["function"]["parameters"].get("required", []))

        assert gemini_required == anthropic_required == openai_required


# ---------------------------------------------------------------------------
# Integration with ToolRegistry.schemas_for_provider
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    """Verify ToolRegistry.schemas_for_provider() uses ToolSchemaConverter."""

    def test_gemini_schemas_are_function_declarations(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        schemas = registry.schemas_for_provider("gemini")

        for schema in schemas:
            assert isinstance(schema, types.FunctionDeclaration)

    def test_anthropic_schemas_have_input_schema(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        schemas = registry.schemas_for_provider("anthropic")

        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"

    def test_mimo_schemas_have_function_wrapper(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        schemas = registry.schemas_for_provider("mimo")

        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "parameters" in schema["function"]

    def test_all_providers_return_same_count(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        gemini = registry.schemas_for_provider("gemini")
        anthropic = registry.schemas_for_provider("anthropic")
        mimo = registry.schemas_for_provider("mimo")

        assert len(gemini) == len(anthropic) == len(mimo)

    def test_unknown_provider_raises(self):
        from src.tools.registry import build_default_registry

        registry = build_default_registry()
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.schemas_for_provider("openai")

"""
src/tools/schema_converter.py
==============================
Centralized tool schema conversion.

Single source of truth for converting Gemini ``FunctionDeclaration``
objects to any provider's native tool format.

Before this module, schema conversion logic was duplicated in three places:
  - ``src/tools/registry.py``               (ToolRegistry._schema_to_dict, _to_openai_schemas)
  - ``src/providers/mimo_provider.py``       (MimoProvider._schema_to_dict)

After this module, all conversion flows through ``ToolSchemaConverter``.

Design rules
------------
* Input is always a ``google.genai.types.FunctionDeclaration``.
* Output is provider-native (Gemini: unchanged, Anthropic: ToolParam dict,
  OpenAI-compat: function-calling dict).
* No imports from providers or registry — this is a leaf dependency.
* All methods are ``@staticmethod`` / ``@classmethod`` — stateless.
"""
from __future__ import annotations

from typing import Any

# Gemini Type enum string → JSON Schema type string
_GENAI_TYPE_TO_JSON: dict[str, str] = {
    "STRING": "string",
    "NUMBER": "number",
    "INTEGER": "integer",
    "BOOLEAN": "boolean",
    "ARRAY": "array",
    "OBJECT": "object",
}


class ToolSchemaConverter:
    """
    Converts Gemini ``FunctionDeclaration`` to provider-native tool formats.

    Usage::

        from src.tools.schema_converter import ToolSchemaConverter

        # For Gemini — no conversion needed
        gemini_schema = ToolSchemaConverter.to_gemini(declaration)

        # For Anthropic — returns ToolParam dict
        anthropic_schema = ToolSchemaConverter.to_anthropic(declaration)

        # For OpenAI-compatible (Mimo, etc.) — returns function-calling dict
        openai_schema = ToolSchemaConverter.to_openai_compat(declaration)
    """

    # ── Internal: Gemini Schema → plain dict ──────────────────────────

    @staticmethod
    def _schema_to_dict(schema: Any) -> dict[str, Any]:
        """
        Recursively convert a ``google.genai.types.Schema`` to a JSON Schema dict.

        Handles the subset of Schema types used in the tool registry:
        OBJECT, STRING, NUMBER, INTEGER, BOOLEAN, ARRAY.
        """
        if schema is None:
            return {"type": "object", "properties": {}}

        raw_type = str(getattr(schema, "type", "OBJECT"))
        # The enum value may be e.g. "Type.STRING" or just "STRING"
        type_str = raw_type.split(".")[-1] if "." in raw_type else raw_type
        json_type = _GENAI_TYPE_TO_JSON.get(type_str.upper(), "string")

        result: dict[str, Any] = {"type": json_type}

        if json_type == "object":
            props = getattr(schema, "properties", {}) or {}
            result["properties"] = {
                name: ToolSchemaConverter._schema_to_dict(prop)
                for name, prop in props.items()
            }
            required = getattr(schema, "required", []) or []
            if required:
                result["required"] = list(required)

        desc = getattr(schema, "description", None)
        if desc:
            result["description"] = desc

        return result

    # ── Public: declaration → provider-native format ──────────────────

    @classmethod
    def to_gemini(cls, declaration: Any) -> Any:
        """
        Gemini needs no conversion — return the ``FunctionDeclaration`` as-is.

        This exists for symmetry so callers can use a uniform dispatch pattern.
        """
        return declaration

    @classmethod
    def to_anthropic(cls, declaration: Any) -> dict[str, Any]:
        """
        Convert a ``FunctionDeclaration`` to an Anthropic ``ToolParam`` dict.

        Anthropic expects::

            {
                "name": "...",
                "description": "...",
                "input_schema": { "type": "object", "properties": {...} }
            }
        """
        input_schema = cls._schema_to_dict(getattr(declaration, "parameters", None))
        # Anthropic requires "properties" and "type": "object" at top level
        input_schema.setdefault("properties", {})
        input_schema["type"] = "object"

        return {
            "name": declaration.name,
            "description": declaration.description or "",
            "input_schema": input_schema,
        }

    @classmethod
    def to_openai_compat(cls, declaration: Any) -> dict[str, Any]:
        """
        Convert a ``FunctionDeclaration`` to OpenAI function-calling format.

        OpenAI expects::

            {
                "type": "function",
                "function": {
                    "name": "...",
                    "description": "...",
                    "parameters": { "type": "object", "properties": {...} }
                }
            }
        """
        params = cls._schema_to_dict(
            getattr(declaration, "parameters", None)
        ) if declaration.parameters else {"type": "object", "properties": {}}

        return {
            "type": "function",
            "function": {
                "name": declaration.name,
                "description": declaration.description or "",
                "parameters": params,
            },
        }

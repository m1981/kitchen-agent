"""
src/tools/registry.py
=====================
Single source of truth for every tool the agent can call.

Each ``ToolEntry`` binds together:
  - ``declaration`` — the typed ``FunctionDeclaration`` sent to the Gemini API.
  - ``fn``          — the Python callable that executes when the model picks
                      that tool.
  - ``category``    — logical grouping for filtering and discovery.

Derived constants (used by agent.py):
  ``FUNCTION_MAP``  — ``{name: callable}`` — looked up at call-dispatch time.
  ``DECLARATIONS``  — ordered list of ``FunctionDeclaration`` objects passed to
                      ``types.Tool(function_declarations=DECLARATIONS)``.

Why this exists
---------------
Previously ``schemas.py`` held raw dicts (no type validation) and ``agent.py``
maintained a separate ``FUNCTION_MAP`` that duplicated every tool name as a
plain string.  A rename in one place silently broke the other.

This module eliminates both problems:
  1. ``FunctionDeclaration`` / ``Schema`` objects validate field names at import
     time — a typo like ``desciption`` raises immediately.
  2. ``FUNCTION_MAP`` is *derived* from the same registry list, so name and
     callable can never drift apart.
  3. ``base_dir`` is fixed inside a lambda so it is never part of the public
     tool API surface (prevents a potential path-traversal vector).

Domain-agnostic design
----------------------
All tool names, descriptions, and parameter examples use generic vocabulary
only.  Domain-specific terminology belongs in the system prompt (``prompts/``),
not in the tool schema that the LLM sees in every request.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable

import structlog
from google.genai import types

from src.config import settings
from src.tools.schema_converter import ToolSchemaConverter

log = structlog.get_logger(__name__)
from src.tools.file_ops import (
    create_file,
    edit_file,
    read_file,
    search_knowledge_base,
)
from src.tools.repo_map import get_repo_map


# ---------------------------------------------------------------------------
# Tool category — for grouping and filtering
# ---------------------------------------------------------------------------

class ToolCategory(Enum):
    """Logical grouping for tools. Used for filtering and discovery."""
    DISCOVERY = auto()
    FILE_OPERATIONS = auto()
    SEARCH = auto()
    NOTES = auto()        # future: note CRUD tools
    WEB = auto()          # future: web search tools


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolEntry:
    """
    Pairs a Gemini FunctionDeclaration with its Python implementation.

    Attributes:
        declaration: The typed FunctionDeclaration sent to the Gemini API.
        fn:          The Python callable that executes when the model picks that tool.
        category:    Logical grouping for filtering and discovery.
        marks_read:  This tool shows the model a file's current content, which
                     satisfies the read-before-edit rule for that path.
        requires_prior_read:
                     This tool rewrites a file and is refused unless the same
                     path was read earlier in the same turn.  The rule lives on
                     the entry, not in the executor, so a new mutating tool
                     opts in by declaring it.
        path_argument:
                     Name of the argument holding the file path, used by the
                     two flags above.
    """

    declaration: types.FunctionDeclaration
    fn: Callable[..., dict]  # type: ignore[type-arg]
    category: ToolCategory = ToolCategory.FILE_OPERATIONS
    marks_read: bool = False
    requires_prior_read: bool = False
    path_argument: str = "filepath"


# ---------------------------------------------------------------------------
# Tool definitions (Ordered: Discovery -> Ingestion -> Mutation)
# ---------------------------------------------------------------------------

_get_repo_map_entry = ToolEntry(
    declaration=types.FunctionDeclaration(
        name="get_repo_map",
        description=(
            "Scans the knowledge base and returns a list of all markdown files and their headers. "
            "ALWAYS use this tool FIRST if the user asks you to read, update, or elaborate on a topic "
            "but does not provide a specific file path. Do not guess file paths."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={},
            required=[],
        ),
    ),
    # base_dir is fixed to settings.data_dir — never exposed to the LLM.
    fn=lambda: get_repo_map(base_dir=str(settings.data_dir)),
    category=ToolCategory.DISCOVERY,
)

def _build_search_entry(
    search_coordinator: Any | None = None,
) -> ToolEntry:
    """
    Build the search_knowledge_base tool entry.

    When a SearchCoordinator is provided, the tool routes through it
    (enabling BM25, embeddings, etc. in the future). Otherwise falls
    back to the raw search_knowledge_base function.
    """
    declaration = types.FunctionDeclaration(
        name="search_knowledge_base",
        description=(
            "Searches all markdown files for lines matching a regex pattern. "
            "Use this when you need to find specific terms, part numbers, or dimensions. "
            "QUERY FORMAT: This tool uses regex. Use pipe (|) for OR logic. "
            "Examples: 'alpha|beta|gamma' finds any of the three terms. "
            "Group the synonyms and product names the user might have used — one "
            "query with several alternatives beats several narrow queries. "
            "IMPORTANT: the knowledge base may contain contradicting notes across files — "
            "use context_lines=3 or higher for ambiguous queries so you can see surrounding "
            "text and detect conflicts before answering. "
            "CITATION: The output shows file paths (=== data/... ===) and line numbers (>> N: ...). "
            "You MUST cite these in your answer under '## Źródła'."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "A regex pattern to search for. Use pipe (|) for OR logic. "
                        "Matching is case-insensitive. "
                        "Examples: 'alpha|beta|gamma' for alternatives, "
                        "'\\d{3,}\\s?mm' for dimensions, 'ZC7S\\w+SA' for part numbers."
                    ),
                ),
                "context_lines": types.Schema(
                    type=types.Type.INTEGER,
                    description=(
                        "Number of lines to include BEFORE and AFTER each matching line "
                        "(default 1). Use 0 for quick counts, 2-3 for ambiguous queries. "
                        "Lower values = smaller output = more room for other tools."
                    ),
                ),
            },
            required=["query"],
        ),
    )

    if search_coordinator is not None:
        # Route through SearchCoordinator — enables future backends
        # (BM25, embeddings) without changing the tool handler.
        def _search_via_coordinator(query: str, context_lines: int = 1) -> dict:
            results = search_coordinator.search(
                query, limit=200, context_lines=context_lines,
            )
            if not results:
                return {"content": f"No matches found for pattern: '{query}'"}
            content = "\n\n".join(r.content for r in results)
            return {"content": content}

        return ToolEntry(
            declaration=declaration,
            fn=_search_via_coordinator,
            category=ToolCategory.SEARCH,
        )

    # Fallback: direct call (backward-compatible, no coordinator)
    return ToolEntry(
        declaration=declaration,
        # base_dir is fixed to settings.data_dir — never exposed to the LLM.
        fn=lambda query, context_lines=1: search_knowledge_base(
            query, base_dir=str(settings.data_dir), context_lines=context_lines
        ),
        category=ToolCategory.SEARCH,
    )


# Module-level default entry (no coordinator — backward compatibility)
_search_knowledge_base_entry = _build_search_entry(search_coordinator=None)

_read_file_entry = ToolEntry(
    declaration=types.FunctionDeclaration(
        name="read_file",
        description=(
            "Reads a markdown file as numbered lines. "
            "CRITICAL: You MUST call this on a path BEFORE you use edit_file on it — "
            "edit_file refuses a file you have not read in this turn. "
            "Returns up to 300 lines per call; the header states which lines you got "
            "and out of how many. When it says the file continues, call again with "
            "offset set to the next line — never edit a file whose end you have not seen. "
            "The 'N: ' prefix is display only: cite those numbers, but NEVER include "
            "them in edit_file's search_text."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "filepath": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Path relative to the knowledge base root, exactly as "
                        "get_repo_map or search_knowledge_base reported it, "
                        "e.g. '01_Proces/notes.md'. A leading 'data/' is accepted. "
                        "Absolute paths and '..' are rejected."
                    ),
                ),
                "offset": types.Schema(
                    type=types.Type.INTEGER,
                    description="First line to return, 1-based. Omit to start at line 1.",
                ),
                "limit": types.Schema(
                    type=types.Type.INTEGER,
                    description="How many lines to return. Omit for the default 300.",
                ),
            },
            required=["filepath"],
        ),
    ),
    # base_dir is fixed to settings.data_dir — never exposed to the LLM.
    fn=lambda filepath, offset=None, limit=None: read_file(
        filepath, base_dir=str(settings.data_dir), offset=offset, limit=limit,
    ),
    category=ToolCategory.FILE_OPERATIONS,
    marks_read=True,
)

_edit_file_entry = ToolEntry(
    declaration=types.FunctionDeclaration(
        name="edit_file",
        description=(
            "Edits an existing file using exact search and replace. "
            "CRITICAL RULES: "
            "1. You MUST know the EXACT existing text. "
            "2. read_file on this exact path is REQUIRED first — this tool is refused "
            "otherwise, and it is refused for good reason: text you have not seen may "
            "match in the wrong place. "
            "3. Copy search_text from the file content WITHOUT the 'N: ' line-number "
            "prefix that read_file adds for display. "
            "4. Make search_text long enough to be unique — every match is replaced. "
            "5. Do not ask the user for the text, find it yourself. "
            "The result contains a unified diff: check it says what you intended."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "filepath": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Path of the file to edit, relative to the knowledge base "
                        "root, e.g. '01_Proces/notes.md'. A leading 'data/' is "
                        "accepted. Absolute paths and '..' are rejected."
                    ),
                ),
                "search_text": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "The EXACT text currently in the file to replace. "
                        "WARNING: This must match character-for-character. Pay strict attention to "
                        "leading/trailing spaces, newlines (\\n), and punctuation."
                    ),
                ),
                "replace_text": types.Schema(
                    type=types.Type.STRING,
                    description="The new text to insert. Ensure you include necessary markdown formatting and newlines.",
                ),
            },
            required=["filepath", "search_text", "replace_text"],
        ),
    ),
    fn=lambda filepath, search_text, replace_text: edit_file(
        filepath, search_text, replace_text,
        backup_dir=settings.data_dir,
        base_dir=str(settings.data_dir),
    ),
    category=ToolCategory.FILE_OPERATIONS,
    requires_prior_read=True,
)

_create_file_entry = ToolEntry(
    declaration=types.FunctionDeclaration(
        name="create_file",
        description=(
            "Creates a brand new markdown file in the knowledge base. "
            "Markdown only — .md is the only accepted extension. When the user asks "
            "for HTML, a form or a printable card, write the document as markdown; "
            "do not try to save .html. "
            "Use this when starting a new topic that does not fit in existing files. "
            "DO NOT use this to update existing files (use edit_file for that). "
            "Call get_repo_map or search_knowledge_base first when you are not sure "
            "the topic already has a file — the result reports any same-named file "
            "found elsewhere. Report the path from the result back to the user, not "
            "the path you asked for."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "filepath": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Path for the new file, relative to the knowledge base root "
                        "(e.g. '02_Projektowanie_i_Style/new-topic.md'). Nested "
                        "directories are created automatically. A leading 'data/' is "
                        "accepted; absolute paths and '..' are rejected. The path "
                        "MUST end in .md — the knowledge base is markdown-only and "
                        "any other extension is refused."
                    ),
                ),
                "content": types.Schema(
                    type=types.Type.STRING,
                    description="The full markdown content to write into the new file.",
                ),
            },
            required=["filepath", "content"],
        ),
    ),
    fn=lambda filepath, content: create_file(
        filepath, content,
        backup_dir=settings.data_dir,
        base_dir=str(settings.data_dir),
    ),
    category=ToolCategory.FILE_OPERATIONS,
)


# ---------------------------------------------------------------------------
# ToolRegistry — class-based interface
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Self-contained tool registry.

    Providers ask for schemas via ``schemas_for_provider()``.
    ToolExecutor asks for handlers via ``get_handler()``.
    No global state. Injectable.
    """

    def __init__(self, tools: list[ToolEntry] | None = None) -> None:
        self._tools: list[ToolEntry] = tools or []

    def register(self, entry: ToolEntry) -> None:
        self._tools.append(entry)

    def get_handler(self, name: str) -> Callable[..., dict]:  # type: ignore[type-arg]
        """Return the callable for a tool by name."""
        for entry in self._tools:
            if entry.declaration.name == name:
                return entry.fn
        raise ValueError(f"Unknown tool: {name!r}")

    @property
    def tool_names(self) -> list[str]:
        return [entry.declaration.name for entry in self._tools]

    def get_all_entries(self) -> list[ToolEntry]:
        return list(self._tools)

    def get_entries_by_category(
        self,
        categories: list[ToolCategory],
    ) -> list[ToolEntry]:
        """Return entries matching the given categories."""
        return [
            entry for entry in self._tools
            if entry.category in categories
        ]

    def schemas_for_provider(
        self,
        provider: str,
        categories: list[ToolCategory] | None = None,
    ) -> list[Any]:
        """
        Return provider-specific tool schemas.

        Delegates to ``ToolSchemaConverter`` for all format conversion.

        Args:
            provider:   "gemini", "anthropic", or "mimo" (OpenAI-compatible).
            categories: Optional filter by tool category.
                        None = return all tools.
        """
        _PROVIDER_FORMATTER = {
            "gemini": ToolSchemaConverter.to_gemini,
            "anthropic": ToolSchemaConverter.to_anthropic,
            "mimo": ToolSchemaConverter.to_openai_compat,
        }

        formatter = _PROVIDER_FORMATTER.get(provider)
        if formatter is None:
            log.error(
                "schemas_for_provider_unknown",
                provider=provider,
                supported=list(_PROVIDER_FORMATTER.keys()),
            )
            raise ValueError(
                f"Unknown provider: {provider!r}. "
                f"Supported: {list(_PROVIDER_FORMATTER.keys())}"
            )

        # Filter by category if specified
        entries = self._tools
        if categories is not None:
            entries = [
                entry for entry in self._tools
                if entry.category in categories
            ]

        return [formatter(entry.declaration) for entry in entries]


def build_default_registry(
    search_coordinator: Any | None = None,
) -> ToolRegistry:
    """
    Factory function — single place to wire all tools.

    Args:
        search_coordinator: Optional SearchCoordinator. When provided the
            search_knowledge_base tool routes through it (enabling BM25,
            embeddings, etc. in the future). When None the tool falls back
            to the raw search_knowledge_base function.

    Import this in DI container, not individual tools.
    """
    registry = ToolRegistry()
    for entry in _ALL_ENTRIES:
        registry.register(entry)

    # If a coordinator is provided, replace the search entry with one
    # that routes through the coordinator.
    if search_coordinator is not None:
        coordinator_entry = _build_search_entry(
            search_coordinator=search_coordinator,
        )
        # Replace the search entry in the registry
        registry._tools = [
            coordinator_entry if e.declaration.name == "search_knowledge_base" else e
            for e in registry._tools
        ]

    return registry


# ---------------------------------------------------------------------------
# Registry — single ordered list; everything else is derived from it
# ---------------------------------------------------------------------------

# Reordered to prime the LLM: Discovery -> Ingestion -> Mutation
_ALL_ENTRIES: list[ToolEntry] = [
    _get_repo_map_entry,
    _search_knowledge_base_entry,
    _read_file_entry,
    _edit_file_entry,
    _create_file_entry,
]



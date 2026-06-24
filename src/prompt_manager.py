"""
src/prompt_manager.py
=====================
F05 — Backend Prompt Management.

Responsibilities
----------------
* Read prompt Markdown files from ``prompts/`` on startup (or on demand).
* Cache them in memory so there is ZERO disk I/O during the hot chat path.
* Expose metadata (id / label / eyebrow) to the frontend via the REST API
  without leaking the full prompt text.
* Resolve a ``mode_id`` → complete ``system_instruction`` string for the LLM.
* Support hot-reload (``reload_prompts()``) so prompt files can be edited
  and picked up immediately without restarting the server.

Domain-agnostic design
----------------------
Mode definitions are loaded from a ``modes.json`` file that lives inside
``prompts_dir``.  This means any domain (kitchen cabinets, legal research,
software engineering, …) can define its own set of modes by:

  1. Writing a ``modes.json`` registry file.
  2. Adding one ``.md`` file per mode.
  3. Optionally providing a ``base_agent_rules.md`` that is prepended to
     every mode's system instruction.

``modes.json`` schema (array of objects)::

    [
      {
        "id":      "research",
        "label":   "Research",
        "eyebrow": "Case law & statutes",
        "file":    "research.md"
      },
      ...
    ]

All four keys (``id``, ``label``, ``eyebrow``, ``file``) are required for
each entry.  Entries missing any key are **silently skipped** (graceful
degradation).  Extra keys are ignored.

Graceful degradation contract
------------------------------
* Missing ``modes.json``          → empty mode list, no crash.
* Malformed JSON in ``modes.json``→ empty mode list, no crash.
* ``modes.json`` root is not list  → empty mode list, no crash.
* Missing mode ``.md`` file       → mode content is empty string (base rules
                                    still prepended).
* Missing ``base_agent_rules.md`` → base rules are empty string.
* Completely missing prompts_dir  → empty base rules + empty mode list.

Design decisions
----------------
* **Singleton at module level** — ``prompt_manager`` is imported directly by
  ``main.py`` for the FastAPI DI factory.  Tests override it via
  ``app.dependency_overrides``.
* **Atomic cache swap** — ``reload_prompts()`` builds a fresh dict and then
  replaces ``self._cache`` in a single assignment so concurrent readers always
  see a consistent snapshot.
* **_MODE_REGISTRY removed** — all domain knowledge now lives in
  ``prompts/modes.json``, not in Python source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Required keys that every modes.json entry must have
# ---------------------------------------------------------------------------

_REQUIRED_ENTRY_KEYS: frozenset[str] = frozenset({"id", "label", "eyebrow", "file"})
_OPTIONAL_BOOL_KEYS: frozenset[str] = frozenset({"tools_enabled"})


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class PromptMode(BaseModel):
    """In-memory representation of one prompt mode."""
    id: str
    label: str
    eyebrow: str
    content: str  # full combined prompt (base rules + mode body) — never sent to frontend
    tools_enabled_default: bool = True  # False → this mode defaults to plain LLM chat


# ---------------------------------------------------------------------------
# PromptManager
# ---------------------------------------------------------------------------

class PromptManager:
    """
    Reads Markdown prompt files once on construction (or on ``reload_prompts``)
    and serves them from an in-memory cache for the rest of the process lifetime.

    Parameters
    ----------
    prompts_dir:
        Directory that contains ``modes.json``, ``base_agent_rules.md``, and
        one ``.md`` file per mode listed in ``modes.json``.
        Defaults to ``"prompts"`` (relative to the working directory).
    """

    def __init__(self, prompts_dir: str = "prompts") -> None:
        self._prompts_dir: Path = Path(prompts_dir)
        self._cache: dict[str, PromptMode] = {}
        self._base_rules: str = ""
        self.reload_prompts()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload_prompts(self) -> None:
        """
        (Re-)read ``modes.json``, ``base_agent_rules.md``, and all mode
        ``.md`` files, then refresh the in-memory cache atomically.

        Safe to call at runtime — replaces ``self._cache`` in a single
        assignment so concurrent readers always see a consistent snapshot.
        Any file that does not exist is treated as an empty string.
        """
        new_cache: dict[str, PromptMode] = {}

        # 1. Load base rules (applied to ALL modes)
        base_rules = self._read_file("base_agent_rules.md")
        self._base_rules = base_rules

        if not self._prompts_dir.exists():
            logger.warning("prompts_dir_missing", path=str(self._prompts_dir))
            self._cache = new_cache
            return

        # 2. Discover mode registry from modes.json (domain-agnostic)
        registry = self._load_mode_registry()

        # 3. Load each mode and combine with base rules
        for entry in registry:
            mode_body = self._read_file(entry["file"])
            separator = "\n\n" if base_rules and mode_body else ""
            full_prompt = f"{base_rules}{separator}{mode_body}".strip()

            # tools_enabled is optional; default True; non-bool coerced to True.
            raw_tools = entry.get("tools_enabled", True)
            tools_default = raw_tools if isinstance(raw_tools, bool) else True

            new_cache[entry["id"]] = PromptMode(
                id=entry["id"],
                label=entry["label"],
                eyebrow=entry["eyebrow"],
                content=full_prompt,
                tools_enabled_default=tools_default,
            )
            logger.debug(
                "prompt_loaded",
                mode_id=entry["id"],
                chars=len(full_prompt),
            )

        # Atomic swap — no reader ever sees a half-built cache
        self._cache = new_cache
        logger.info("prompts_reloaded", mode_count=len(self._cache))

    def get_all_modes(self) -> list[dict]:
        """
        Returns metadata for every cached mode **in registry order**.

        **Never includes ``content``** — only ``id``, ``label``, ``eyebrow``,
        and ``tools_enabled_default`` are returned so the frontend knows which
        buttons to render and what the default tool behaviour is for each mode.
        """
        return [
            {
                "id":                   mode.id,
                "label":                mode.label,
                "eyebrow":              mode.eyebrow,
                "tools_enabled_default": mode.tools_enabled_default,
            }
            for mode in self._cache.values()
        ]

    def get_mode(self, mode_id: str) -> PromptMode | None:
        """Return the full ``PromptMode`` for *mode_id*, or ``None`` if unknown."""
        return self._cache.get(mode_id)

    def get_system_instruction(self, mode_id: str) -> str:
        """
        Returns the full system instruction string for the given ``mode_id``.

        Falls back to ``_base_rules`` when the mode is unknown so the LLM
        always has at least the base agentic rules, even for unknown modes.
        """
        mode = self._cache.get(mode_id)
        if mode is not None:
            return mode.content
        logger.warning("unknown_mode_id_fallback", mode_id=mode_id)
        return self._base_rules

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_mode_registry(self) -> list[dict[str, str]]:
        """
        Parse ``modes.json`` from ``prompts_dir`` and return a validated list
        of mode entry dicts.  Any entry missing a required key is skipped.
        Returns ``[]`` on any error (missing file, malformed JSON, wrong type).
        """
        modes_path = self._prompts_dir / "modes.json"
        if not modes_path.exists():
            logger.debug("modes_json_missing", path=str(modes_path))
            return []

        raw_text = modes_path.read_text(encoding="utf-8")

        try:
            data: Any = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.warning("modes_json_parse_error", path=str(modes_path), error=str(exc))
            return []

        if not isinstance(data, list):
            logger.warning(
                "modes_json_not_a_list",
                path=str(modes_path),
                type=type(data).__name__,
            )
            return []

        valid_entries: list[dict[str, str]] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                logger.warning("modes_json_entry_not_dict", index=i, type=type(item).__name__)
                continue
            missing = _REQUIRED_ENTRY_KEYS - item.keys()
            if missing:
                logger.warning(
                    "modes_json_entry_missing_keys",
                    index=i,
                    missing=sorted(missing),
                )
                continue
            # Include required keys plus the optional tools_enabled flag.
            entry: dict = {
                "id":      str(item["id"]),
                "label":   str(item["label"]),
                "eyebrow": str(item["eyebrow"]),
                "file":    str(item["file"]),
            }
            if "tools_enabled" in item:
                entry["tools_enabled"] = item["tools_enabled"]
            valid_entries.append(entry)

        return valid_entries

    def _read_file(self, filename: str) -> str:
        """Read a file relative to ``prompts_dir``; return '' if absent."""
        filepath = self._prompts_dir / filename
        if not filepath.exists():
            logger.debug("prompt_file_missing", path=str(filepath))
            return ""
        return filepath.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

# Instantiated once when the module is first imported.
# main.py uses this via the get_prompt_manager() DI factory.
# Tests override it via app.dependency_overrides[get_prompt_manager].
prompt_manager = PromptManager()

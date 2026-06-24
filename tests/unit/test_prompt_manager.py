"""
tests/test_prompt_manager.py
============================
TDD tests for PromptManager (F05 — Backend Prompt Management).

Tests are written RED-first before the implementation exists.

Coverage contract:
  - PromptManager loads and caches prompt files from a directory
  - modes.json drives which modes are registered (domain-agnostic)
  - base_agent_rules.md is prepended to every mode's content
  - get_all_modes() returns metadata only (no content)
  - get_system_instruction() returns the full combined prompt
  - get_system_instruction() falls back to base rules for unknown mode_id
  - reload_prompts() hot-swaps the in-memory cache without restart
  - Missing files produce empty strings (graceful degradation)
  - A missing prompts_dir does not crash; returns empty cache + empty base rules
"""
import json
from pathlib import Path

import pytest

from src.prompt_manager import PromptManager, PromptMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KITCHEN_MODES = [
    {"id": "general",  "label": "General",  "eyebrow": "Workspace help",       "file": "general.md"},
    {"id": "design",   "label": "Design",   "eyebrow": "Ergonomics and layout", "file": "design.md"},
    {"id": "assembly", "label": "Assembly", "eyebrow": "Build and fitting",     "file": "assembly.md"},
]


def _write(directory: Path, filename: str, text: str) -> None:
    """Convenience: write a file inside *directory*, creating parents."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(text, encoding="utf-8")


def _write_kitchen_modes(directory: Path) -> None:
    """Write the standard kitchen modes.json into *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "modes.json").write_text(json.dumps(_KITCHEN_MODES), encoding="utf-8")


# ---------------------------------------------------------------------------
# PromptMode model
# ---------------------------------------------------------------------------

def test_prompt_mode_fields() -> None:
    """PromptMode must expose id, label, eyebrow, and content."""
    mode = PromptMode(id="general", label="General", eyebrow="Workspace help", content="Hello.")
    assert mode.id == "general"
    assert mode.label == "General"
    assert mode.eyebrow == "Workspace help"
    assert mode.content == "Hello."


# ---------------------------------------------------------------------------
# PromptManager — basic loading
# ---------------------------------------------------------------------------

def test_manager_loads_base_rules(tmp_path: Path) -> None:
    """base_agent_rules.md should be read and stored in _base_rules."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "RULE: Never edit without reading first.\n")
    _write(tmp_path, "general.md", "You are a general assistant.\n")
    _write(tmp_path, "design.md",   "d\n")
    _write(tmp_path, "assembly.md", "a\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    assert "RULE: Never edit without reading first." in mgr._base_rules


def test_manager_combines_base_rules_and_mode_content(tmp_path: Path) -> None:
    """Full prompt must contain both base rules and mode-specific content."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "BASE RULES HERE\n")
    _write(tmp_path, "general.md",  "g\n")
    _write(tmp_path, "design.md", "DESIGN MODE CONTENT\n")
    _write(tmp_path, "assembly.md", "a\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    instruction = mgr.get_system_instruction("design")

    assert "BASE RULES HERE" in instruction
    assert "DESIGN MODE CONTENT" in instruction


def test_manager_loads_all_three_modes(tmp_path: Path) -> None:
    """All three built-in modes (general, design, assembly) must be in cache."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "base\n")
    _write(tmp_path, "general.md",  "general content\n")
    _write(tmp_path, "design.md",   "design content\n")
    _write(tmp_path, "assembly.md", "assembly content\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    modes = mgr.get_all_modes()
    ids = {m["id"] for m in modes}

    assert ids == {"general", "design", "assembly"}


# ---------------------------------------------------------------------------
# get_all_modes()
# ---------------------------------------------------------------------------

def test_get_all_modes_returns_metadata_only(tmp_path: Path) -> None:
    """get_all_modes() must return id/label/eyebrow dicts WITHOUT content."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "base\n")
    _write(tmp_path, "general.md", "secret prompt text\n")
    _write(tmp_path, "design.md",  "secret design text\n")
    _write(tmp_path, "assembly.md","secret assembly text\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    for mode_dict in mgr.get_all_modes():
        assert "content" not in mode_dict, "content must not be exposed via get_all_modes()"
        assert "id" in mode_dict
        assert "label" in mode_dict
        assert "eyebrow" in mode_dict


def test_get_all_modes_correct_labels(tmp_path: Path) -> None:
    """Labels and eyebrows must match the spec in modes.json."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "x\n")
    _write(tmp_path, "general.md",  "x\n")
    _write(tmp_path, "design.md",   "x\n")
    _write(tmp_path, "assembly.md", "x\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    by_id = {m["id"]: m for m in mgr.get_all_modes()}

    assert by_id["general"]["label"]  == "General"
    assert by_id["design"]["label"]   == "Design"
    assert by_id["assembly"]["label"] == "Assembly"

    assert by_id["general"]["eyebrow"]  == "Workspace help"
    assert by_id["design"]["eyebrow"]   == "Ergonomics and layout"
    assert by_id["assembly"]["eyebrow"] == "Build and fitting"


# ---------------------------------------------------------------------------
# get_system_instruction()
# ---------------------------------------------------------------------------

def test_get_system_instruction_known_mode(tmp_path: Path) -> None:
    """Returns the full combined prompt for a known mode_id."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "BASE\n")
    _write(tmp_path, "general.md",  "GENERAL\n")
    _write(tmp_path, "design.md",   "DESIGN\n")
    _write(tmp_path, "assembly.md", "ASSEMBLY\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))

    assert "BASE" in mgr.get_system_instruction("general")
    assert "GENERAL" in mgr.get_system_instruction("general")

    assert "BASE" in mgr.get_system_instruction("design")
    assert "DESIGN" in mgr.get_system_instruction("design")

    assert "BASE" in mgr.get_system_instruction("assembly")
    assert "ASSEMBLY" in mgr.get_system_instruction("assembly")


def test_get_system_instruction_unknown_mode_fallback(tmp_path: Path) -> None:
    """Unknown mode_id must fall back to base rules only, never crash."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "FALLBACK BASE RULES\n")
    _write(tmp_path, "general.md", "x\n")
    _write(tmp_path, "design.md",  "x\n")
    _write(tmp_path, "assembly.md","x\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    result = mgr.get_system_instruction("totally_unknown_mode")

    assert "FALLBACK BASE RULES" in result


def test_get_system_instruction_returns_string(tmp_path: Path) -> None:
    """Return type must always be str."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "base\n")
    _write(tmp_path, "general.md", "g\n")
    _write(tmp_path, "design.md",  "d\n")
    _write(tmp_path, "assembly.md","a\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    assert isinstance(mgr.get_system_instruction("general"), str)
    assert isinstance(mgr.get_system_instruction("unknown"), str)


# ---------------------------------------------------------------------------
# Graceful degradation — missing files / directory
# ---------------------------------------------------------------------------

def test_missing_base_rules_file_graceful(tmp_path: Path) -> None:
    """If base_agent_rules.md is absent, the manager must not crash.
    The mode content alone is returned for known modes."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "general.md", "GENERAL ONLY\n")
    _write(tmp_path, "design.md",  "x\n")
    _write(tmp_path, "assembly.md","x\n")
    # NOTE: base_agent_rules.md intentionally NOT created

    mgr = PromptManager(prompts_dir=str(tmp_path))
    result = mgr.get_system_instruction("general")
    assert "GENERAL ONLY" in result
    assert mgr._base_rules == ""


def test_missing_mode_file_graceful(tmp_path: Path) -> None:
    """If a mode .md file is absent, its content is empty string (no crash).
    The combined prompt still contains the base rules."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "BASE RULES\n")
    _write(tmp_path, "general.md",  "g\n")
    # design.md intentionally missing
    _write(tmp_path, "assembly.md", "a\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    result = mgr.get_system_instruction("design")
    # Base rules must still be present
    assert "BASE RULES" in result


def test_missing_prompts_dir_graceful(tmp_path: Path) -> None:
    """A completely absent prompts_dir should not crash; returns empty cache."""
    non_existent = tmp_path / "does_not_exist"
    mgr = PromptManager(prompts_dir=str(non_existent))

    assert mgr._base_rules == ""
    assert mgr.get_all_modes() == []
    # Unknown mode returns empty string (base rules are empty)
    assert mgr.get_system_instruction("general") == ""


# ---------------------------------------------------------------------------
# reload_prompts() — hot-swap
# ---------------------------------------------------------------------------

def test_reload_prompts_picks_up_new_content(tmp_path: Path) -> None:
    """After reload_prompts(), updated file content must be reflected immediately."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "ORIGINAL BASE\n")
    _write(tmp_path, "general.md",  "ORIGINAL GENERAL\n")
    _write(tmp_path, "design.md",   "x\n")
    _write(tmp_path, "assembly.md", "x\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    assert "ORIGINAL GENERAL" in mgr.get_system_instruction("general")

    # Simulate file edit
    (tmp_path / "general.md").write_text("UPDATED GENERAL\n", encoding="utf-8")
    mgr.reload_prompts()

    result = mgr.get_system_instruction("general")
    assert "UPDATED GENERAL" in result
    assert "ORIGINAL GENERAL" not in result


def test_reload_prompts_picks_up_new_base_rules(tmp_path: Path) -> None:
    """After reload_prompts(), updated base rules must appear in all modes."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "OLD BASE\n")
    _write(tmp_path, "general.md",  "g\n")
    _write(tmp_path, "design.md",   "d\n")
    _write(tmp_path, "assembly.md", "a\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    assert "OLD BASE" in mgr.get_system_instruction("design")

    (tmp_path / "base_agent_rules.md").write_text("NEW BASE\n", encoding="utf-8")
    mgr.reload_prompts()

    assert "NEW BASE" in mgr.get_system_instruction("design")
    assert "OLD BASE" not in mgr.get_system_instruction("design")


def test_reload_clears_old_cache(tmp_path: Path) -> None:
    """reload_prompts() must clear and fully rebuild the cache (no stale entries)."""
    _write_kitchen_modes(tmp_path)
    _write(tmp_path, "base_agent_rules.md", "base\n")
    _write(tmp_path, "general.md",  "g\n")
    _write(tmp_path, "design.md",   "d\n")
    _write(tmp_path, "assembly.md", "a\n")

    mgr = PromptManager(prompts_dir=str(tmp_path))
    assert len(mgr.get_all_modes()) == 3

    mgr.reload_prompts()
    # Must still have exactly 3 modes after reload, not 6 (no duplicates)
    assert len(mgr.get_all_modes()) == 3


# ---------------------------------------------------------------------------
# Singleton pattern
# ---------------------------------------------------------------------------

def test_singleton_prompt_manager_is_importable() -> None:
    """The module-level singleton `prompt_manager` must be importable."""
    from src.prompt_manager import prompt_manager  # noqa: F401 (existence check)
    assert prompt_manager is not None

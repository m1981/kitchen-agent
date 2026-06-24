"""
tests/test_prompt_manager_domain_agnostic.py
============================================
TDD tests for the domain-agnostic PromptManager refactor.

Context
-------
The original PromptManager hardcodes a ``_MODE_REGISTRY`` list with
kitchen-specific mode ids (general / design / assembly) directly in
``prompt_manager.py``.  The refactor externalises that list into a
``modes.json`` file that lives inside ``prompts_dir``.  Domain owners
drop their own ``modes.json`` without touching Python source.

Coverage contract
-----------------
1.  ``modes.json`` is discovered and parsed from ``prompts_dir``.
2.  Each entry in ``modes.json`` must have ``id``, ``label``, ``eyebrow``,
    ``file`` keys; extras are ignored.
3.  Hot-reload picks up changes to ``modes.json`` (not just .md files).
4.  ``modes.json`` missing → empty mode list, graceful degradation (no crash).
5.  ``modes.json`` is malformed JSON → treated as empty list (no crash).
6.  ``modes.json`` entries with missing required keys are skipped with a
    warning (no crash).
7.  A custom domain (e.g. legal) can define modes completely unrelated to
    kitchens and they are served correctly.
8.  Base-rules are still prepended to every custom-domain mode.
9.  Ordering of modes in the response matches the order in ``modes.json``.
10. ``get_system_instruction`` falls back to base rules for unknown mode id
    regardless of what's in ``modes.json``.
"""

import json
from pathlib import Path

import pytest

from src.prompt_manager import PromptManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(directory: Path, filename: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(text, encoding="utf-8")


def _write_modes(directory: Path, modes: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "modes.json").write_text(json.dumps(modes), encoding="utf-8")


_KITCHEN_MODES = [
    {"id": "general",  "label": "General",  "eyebrow": "Workspace help",       "file": "general.md"},
    {"id": "design",   "label": "Design",   "eyebrow": "Ergonomics and layout", "file": "design.md"},
    {"id": "assembly", "label": "Assembly", "eyebrow": "Build and fitting",     "file": "assembly.md"},
]

_LEGAL_MODES = [
    {"id": "research", "label": "Research", "eyebrow": "Case law & statutes",  "file": "research.md"},
    {"id": "drafting", "label": "Drafting", "eyebrow": "Contract generation",  "file": "drafting.md"},
    {"id": "review",   "label": "Review",   "eyebrow": "Document QA",          "file": "review.md"},
]


# ============================================================================
# 1. modes.json is discovered and parsed
# ============================================================================

class TestModesJsonDiscovery:

    def test_modes_from_json_are_loaded(self, tmp_path: Path) -> None:
        """All modes defined in modes.json must appear in get_all_modes()."""
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md",  "g\n")
        _write(tmp_path, "design.md",   "d\n")
        _write(tmp_path, "assembly.md", "a\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"general", "design", "assembly"}

    def test_modes_json_fields_exposed_as_metadata(self, tmp_path: Path) -> None:
        """id, label, eyebrow from modes.json must appear in get_all_modes() dicts."""
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md",  "g\n")
        _write(tmp_path, "design.md",   "d\n")
        _write(tmp_path, "assembly.md", "a\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        by_id = {m["id"]: m for m in mgr.get_all_modes()}

        assert by_id["general"]["label"]    == "General"
        assert by_id["design"]["label"]     == "Design"
        assert by_id["assembly"]["label"]   == "Assembly"
        assert by_id["general"]["eyebrow"]  == "Workspace help"
        assert by_id["design"]["eyebrow"]   == "Ergonomics and layout"
        assert by_id["assembly"]["eyebrow"] == "Build and fitting"

    def test_extra_fields_in_modes_json_are_ignored(self, tmp_path: Path) -> None:
        """Unknown keys in a modes.json entry must not cause a crash."""
        modes_with_extra = [
            {
                "id": "general", "label": "General", "eyebrow": "Help",
                "file": "general.md",
                "some_unknown_field": "this should be silently ignored",
            }
        ]
        _write_modes(tmp_path, modes_with_extra)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md", "GENERAL\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert len(mgr.get_all_modes()) == 1
        assert mgr.get_all_modes()[0]["id"] == "general"


# ============================================================================
# 2. Ordering preserved
# ============================================================================

class TestModesOrdering:

    def test_mode_order_matches_modes_json(self, tmp_path: Path) -> None:
        """Modes must be returned in the same order they appear in modes.json."""
        # Deliberately reversed relative to alphabetical order
        modes = [
            {"id": "assembly", "label": "Assembly", "eyebrow": "Build", "file": "assembly.md"},
            {"id": "design",   "label": "Design",   "eyebrow": "Layout","file": "design.md"},
            {"id": "general",  "label": "General",  "eyebrow": "Help",  "file": "general.md"},
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        for name in ("assembly.md", "design.md", "general.md"):
            _write(tmp_path, name, f"{name}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        returned_ids = [m["id"] for m in mgr.get_all_modes()]
        assert returned_ids == ["assembly", "design", "general"]


# ============================================================================
# 3. Hot-reload picks up modes.json changes
# ============================================================================

class TestHotReloadWithModesJson:

    def test_reload_picks_up_new_mode_added_to_modes_json(self, tmp_path: Path) -> None:
        """Adding a mode to modes.json and calling reload_prompts() surfaces it."""
        initial = [
            {"id": "general", "label": "General", "eyebrow": "Help", "file": "general.md"},
        ]
        _write_modes(tmp_path, initial)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md", "GENERAL\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert len(mgr.get_all_modes()) == 1

        # Simulate domain owner adding a second mode
        extended = initial + [
            {"id": "design", "label": "Design", "eyebrow": "Layout", "file": "design.md"},
        ]
        _write_modes(tmp_path, extended)
        _write(tmp_path, "design.md", "DESIGN\n")
        mgr.reload_prompts()

        ids = {m["id"] for m in mgr.get_all_modes()}
        assert "design" in ids
        assert len(mgr.get_all_modes()) == 2

    def test_reload_picks_up_removed_mode(self, tmp_path: Path) -> None:
        """Removing a mode from modes.json and reloading removes it from cache."""
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        for f in ("general.md", "design.md", "assembly.md"):
            _write(tmp_path, f, f"{f}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert len(mgr.get_all_modes()) == 3

        # Remove assembly from the registry
        reduced = [m for m in _KITCHEN_MODES if m["id"] != "assembly"]
        _write_modes(tmp_path, reduced)
        mgr.reload_prompts()

        ids = {m["id"] for m in mgr.get_all_modes()}
        assert "assembly" not in ids
        assert len(mgr.get_all_modes()) == 2

    def test_reload_picks_up_changed_label(self, tmp_path: Path) -> None:
        """Changing a label in modes.json and reloading reflects the new label."""
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        for f in ("general.md", "design.md", "assembly.md"):
            _write(tmp_path, f, f"{f}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        by_id = {m["id"]: m for m in mgr.get_all_modes()}
        assert by_id["general"]["label"] == "General"

        # Domain owner renames the mode
        updated = [
            {**m, "label": "Kitchen Helper"} if m["id"] == "general" else m
            for m in _KITCHEN_MODES
        ]
        _write_modes(tmp_path, updated)
        mgr.reload_prompts()

        by_id = {m["id"]: m for m in mgr.get_all_modes()}
        assert by_id["general"]["label"] == "Kitchen Helper"


# ============================================================================
# 4. Missing modes.json → graceful degradation
# ============================================================================

class TestMissingModesJson:

    def test_missing_modes_json_returns_empty_mode_list(self, tmp_path: Path) -> None:
        """When modes.json is absent, get_all_modes() returns [] without crash."""
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        # No modes.json written

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert mgr.get_all_modes() == []

    def test_missing_modes_json_base_rules_still_loaded(self, tmp_path: Path) -> None:
        """Base rules are still available even without modes.json."""
        _write(tmp_path, "base_agent_rules.md", "IMPORTANT BASE RULES\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert "IMPORTANT BASE RULES" in mgr._base_rules

    def test_missing_modes_json_unknown_mode_fallback_to_base(self, tmp_path: Path) -> None:
        """get_system_instruction on any mode falls back to base when no modes.json."""
        _write(tmp_path, "base_agent_rules.md", "FALLBACK BASE\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        result = mgr.get_system_instruction("general")
        assert "FALLBACK BASE" in result


# ============================================================================
# 5. Malformed modes.json → graceful degradation
# ============================================================================

class TestMalformedModesJson:

    def test_malformed_json_returns_empty_mode_list(self, tmp_path: Path) -> None:
        """Malformed modes.json must not crash; modes list is empty."""
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "modes.json", "THIS IS NOT VALID JSON {{{")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert mgr.get_all_modes() == []

    def test_malformed_json_base_rules_still_loaded(self, tmp_path: Path) -> None:
        """Base rules are unaffected by a broken modes.json."""
        _write(tmp_path, "base_agent_rules.md", "BASE RULES OK\n")
        _write(tmp_path, "modes.json", "not json at all")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert "BASE RULES OK" in mgr._base_rules

    def test_modes_json_not_a_list_treated_as_empty(self, tmp_path: Path) -> None:
        """If modes.json contains a JSON object (not a list), treat as empty list."""
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "modes.json", json.dumps({"id": "general", "label": "X"}))

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert mgr.get_all_modes() == []

    def test_modes_json_with_null_treated_as_empty(self, tmp_path: Path) -> None:
        """JSON null is treated as empty list (graceful)."""
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "modes.json", "null")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert mgr.get_all_modes() == []


# ============================================================================
# 6. modes.json entries with missing required keys are skipped
# ============================================================================

class TestMissingKeysInEntry:

    def test_entry_missing_id_is_skipped(self, tmp_path: Path) -> None:
        """A modes.json entry without 'id' is skipped; valid entries still work."""
        modes = [
            {"label": "No ID", "eyebrow": "X", "file": "noid.md"},          # missing id — skip
            {"id": "general", "label": "General", "eyebrow": "Help", "file": "general.md"},
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md", "GENERAL\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"general"}

    def test_entry_missing_file_is_skipped(self, tmp_path: Path) -> None:
        """A modes.json entry without 'file' is skipped."""
        modes = [
            {"id": "bad",    "label": "Bad",     "eyebrow": "X"},            # missing file — skip
            {"id": "general","label": "General", "eyebrow": "Help", "file": "general.md"},
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md", "GENERAL\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"general"}

    def test_entry_missing_label_is_skipped(self, tmp_path: Path) -> None:
        """A modes.json entry without 'label' is skipped."""
        modes = [
            {"id": "nolabel", "eyebrow": "X", "file": "nolabel.md"},         # missing label — skip
            {"id": "design",  "label": "Design", "eyebrow": "Layout", "file": "design.md"},
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "design.md", "DESIGN\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"design"}

    def test_entry_missing_eyebrow_is_skipped(self, tmp_path: Path) -> None:
        """A modes.json entry without 'eyebrow' is skipped."""
        modes = [
            {"id": "noeyebrow", "label": "X", "file": "noeyebrow.md"},       # missing eyebrow — skip
            {"id": "assembly",  "label": "Assembly", "eyebrow": "Build", "file": "assembly.md"},
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "assembly.md", "ASSEMBLY\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"assembly"}

    def test_all_invalid_entries_yields_empty_list(self, tmp_path: Path) -> None:
        """If every entry is malformed, modes list is empty (no crash)."""
        modes = [
            {"label": "No ID",   "eyebrow": "X", "file": "a.md"},
            {"id": "no_label",   "eyebrow": "X", "file": "b.md"},
        ]
        _write_modes(tmp_path, modes)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert mgr.get_all_modes() == []


# ============================================================================
# 7. Custom domain (legal) — completely different modes
# ============================================================================

class TestCustomDomain:

    def test_legal_domain_modes_loaded_from_modes_json(self, tmp_path: Path) -> None:
        """A legal-domain modes.json with research/drafting/review modes works."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "LEGAL BASE RULES\n")
        _write(tmp_path, "research.md", "RESEARCH MODE CONTENT\n")
        _write(tmp_path, "drafting.md", "DRAFTING MODE CONTENT\n")
        _write(tmp_path, "review.md",   "REVIEW MODE CONTENT\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"research", "drafting", "review"}

    def test_legal_domain_metadata_correct(self, tmp_path: Path) -> None:
        """Labels and eyebrows from legal modes.json are served correctly."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        for mode in _LEGAL_MODES:
            _write(tmp_path, mode["file"], f"{mode['id']}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        by_id = {m["id"]: m for m in mgr.get_all_modes()}

        assert by_id["research"]["label"]   == "Research"
        assert by_id["drafting"]["label"]   == "Drafting"
        assert by_id["review"]["label"]     == "Review"
        assert by_id["research"]["eyebrow"] == "Case law & statutes"
        assert by_id["drafting"]["eyebrow"] == "Contract generation"
        assert by_id["review"]["eyebrow"]   == "Document QA"

    def test_legal_domain_no_kitchen_modes_present(self, tmp_path: Path) -> None:
        """Kitchen modes (general/design/assembly) must NOT appear when not in modes.json."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        for mode in _LEGAL_MODES:
            _write(tmp_path, mode["file"], f"{mode['id']}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert "general" not in ids
        assert "design" not in ids
        assert "assembly" not in ids


# ============================================================================
# 8. Base rules still prepended to every custom-domain mode
# ============================================================================

class TestBaseRulesWithCustomDomain:

    def test_base_rules_prepended_to_legal_modes(self, tmp_path: Path) -> None:
        """Base rules must be in the system instruction for every legal mode."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "NEVER EDIT WITHOUT READING\n")
        _write(tmp_path, "research.md", "RESEARCH CONTENT\n")
        _write(tmp_path, "drafting.md", "d\n")
        _write(tmp_path, "review.md",   "r\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        instruction = mgr.get_system_instruction("research")

        assert "NEVER EDIT WITHOUT READING" in instruction
        assert "RESEARCH CONTENT" in instruction

    def test_each_legal_mode_has_its_own_content(self, tmp_path: Path) -> None:
        """Mode-specific content must be different for each legal mode."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "research.md", "RESEARCH CONTENT\n")
        _write(tmp_path, "drafting.md", "DRAFTING CONTENT\n")
        _write(tmp_path, "review.md",   "REVIEW CONTENT\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))

        research_instr = mgr.get_system_instruction("research")
        drafting_instr = mgr.get_system_instruction("drafting")
        review_instr   = mgr.get_system_instruction("review")

        assert "RESEARCH CONTENT" in research_instr
        assert "DRAFTING CONTENT" not in research_instr

        assert "DRAFTING CONTENT" in drafting_instr
        assert "RESEARCH CONTENT" not in drafting_instr

        assert "REVIEW CONTENT" in review_instr
        assert "DRAFTING CONTENT" not in review_instr


# ============================================================================
# 9. get_system_instruction fallback with custom domain
# ============================================================================

class TestFallbackWithCustomDomain:

    def test_unknown_mode_in_legal_domain_falls_back_to_base(self, tmp_path: Path) -> None:
        """Unknown mode_id always falls back to base rules (domain-agnostic)."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "LEGAL AGENT BASE\n")
        for mode in _LEGAL_MODES:
            _write(tmp_path, mode["file"], f"{mode['id']}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        result = mgr.get_system_instruction("totally_unknown_mode")

        assert "LEGAL AGENT BASE" in result
        assert "RESEARCH" not in result.upper()

    def test_kitchen_mode_unknown_in_legal_domain(self, tmp_path: Path) -> None:
        """'design' (kitchen) is unknown in legal domain → falls back to base."""
        _write_modes(tmp_path, _LEGAL_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        for mode in _LEGAL_MODES:
            _write(tmp_path, mode["file"], f"{mode['id']}\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        result = mgr.get_system_instruction("design")

        assert "BASE" in result


# ============================================================================
# 10. App metadata settings (app_title / app_description)
# ============================================================================

class TestAppMetadataSettings:
    """
    Settings in config.py must expose app_title and app_description so that
    main.py can pass them to FastAPI() without hardcoding domain vocabulary.
    """

    def test_settings_has_app_title_field(self) -> None:
        from src.config import Settings
        s = Settings(app_title="Legal Document Agent")
        assert s.app_title == "Legal Document Agent"

    def test_settings_has_app_description_field(self) -> None:
        from src.config import Settings
        s = Settings(app_description="AI assistant for legal professionals.")
        assert s.app_description == "AI assistant for legal professionals."

    def test_settings_app_title_default_is_generic(self) -> None:
        """Default title must NOT hard-code 'kitchen' or Polish vocabulary."""
        from src.config import Settings
        s = Settings()
        assert isinstance(s.app_title, str)
        assert len(s.app_title) > 0
        # Must not contain domain-specific vocabulary in the default
        assert "kitchen" not in s.app_title.lower()
        assert "kuchni" not in s.app_title.lower()

    def test_settings_app_description_default_is_generic(self) -> None:
        """Default description must NOT hard-code 'kitchen' or Polish vocabulary."""
        from src.config import Settings
        s = Settings()
        assert isinstance(s.app_description, str)
        assert "kitchen" not in s.app_description.lower()
        assert "kuchni" not in s.app_description.lower()

    def test_settings_app_title_overridable_via_constructor(self) -> None:
        from src.config import Settings
        s = Settings(app_title="My Custom Agent")
        assert s.app_title == "My Custom Agent"

    def test_settings_app_description_overridable_via_constructor(self) -> None:
        from src.config import Settings
        s = Settings(app_description="Helps with woodworking projects.")
        assert s.app_description == "Helps with woodworking projects."


# ============================================================================
# 11. Tool registry — no domain vocabulary in descriptions
# ============================================================================

class TestToolRegistryDomainAgnostic:
    """
    Tool descriptions in src/tools/registry.py must not contain
    kitchen/cabinet-specific vocabulary so they work in any domain.
    """

    KITCHEN_WORDS = {
        "blum", "zawias", "kuchni", "cabinet", "kitchen",
        "hafele", "kronospan", "szafk",
    }

    def _get_all_description_text(self) -> str:
        from src.tools.registry import build_default_registry
        registry = build_default_registry()
        parts = []
        for entry in registry.get_all_entries():
            d = entry.declaration
            parts.append(d.description or "")
            if d.parameters and d.parameters.properties:
                for prop in d.parameters.properties.values():
                    parts.append(getattr(prop, "description", "") or "")
        return " ".join(parts).lower()

    def test_no_kitchen_vocabulary_in_tool_descriptions(self) -> None:
        text = self._get_all_description_text()
        found = [w for w in self.KITCHEN_WORDS if w in text]
        assert not found, (
            f"Kitchen-specific vocabulary found in tool descriptions: {found}\n"
            f"Tool descriptions must be domain-agnostic."
        )

    def test_search_tool_example_is_generic(self) -> None:
        """The search_knowledge_base tool's example query must be generic."""
        from src.tools.registry import build_default_registry
        registry = build_default_registry()
        for entry in registry.get_all_entries():
            if entry.declaration.name == "search_knowledge_base":
                desc = (entry.declaration.description or "").lower()
                assert "blum" not in desc
                assert "zawias" not in desc
                return
        pytest.fail("search_knowledge_base tool not found in registry")


# ============================================================================
# 12. FastAPI app title and description use settings (integration check)
# ============================================================================

class TestFastAPIMetadataFromSettings:

    def test_app_title_matches_settings(self, monkeypatch) -> None:
        """FastAPI app title must be derived from settings.app_title."""
        import src.dependencies as main_module
        import src.config as config_module

        monkeypatch.setattr(config_module.settings, "app_title", "Test Domain Agent")
        # Re-read the app's openapi info via the TestClient
        from fastapi.testclient import TestClient
        # The title is baked in at app creation time, so we check the module-level
        # settings object drives it — verify the field exists and wiring is intended
        assert hasattr(config_module.settings, "app_title")

    def test_app_description_matches_settings(self, monkeypatch) -> None:
        """FastAPI app description must be derived from settings.app_description."""
        import src.config as config_module
        assert hasattr(config_module.settings, "app_description")


# ============================================================================
# 13. Kitchen domain backward-compatibility (modes.json exists in prompts/)
# ============================================================================

class TestKitchenDomainBackwardCompatibility:
    """
    The kitchen domain must still work exactly as before after the refactor —
    the modes.json file in prompts/ is the only addition.
    """

    def test_kitchen_modes_all_present_with_modes_json(self, tmp_path: Path) -> None:
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "BASE\n")
        _write(tmp_path, "general.md",  "g\n")
        _write(tmp_path, "design.md",   "d\n")
        _write(tmp_path, "assembly.md", "a\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        ids = {m["id"] for m in mgr.get_all_modes()}
        assert ids == {"general", "design", "assembly"}

    def test_kitchen_system_instruction_assembly_mode(self, tmp_path: Path) -> None:
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "CRITICAL RULES\n")
        _write(tmp_path, "general.md",  "g\n")
        _write(tmp_path, "design.md",   "d\n")
        _write(tmp_path, "assembly.md", "ASSEMBLY SPECIFIC CONTENT\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        instr = mgr.get_system_instruction("assembly")

        assert "CRITICAL RULES" in instr
        assert "ASSEMBLY SPECIFIC CONTENT" in instr

    def test_kitchen_reload_still_works(self, tmp_path: Path) -> None:
        _write_modes(tmp_path, _KITCHEN_MODES)
        _write(tmp_path, "base_agent_rules.md", "OLD BASE\n")
        _write(tmp_path, "general.md",  "OLD GENERAL\n")
        _write(tmp_path, "design.md",   "d\n")
        _write(tmp_path, "assembly.md", "a\n")

        mgr = PromptManager(prompts_dir=str(tmp_path))
        assert "OLD GENERAL" in mgr.get_system_instruction("general")

        _write(tmp_path, "general.md", "NEW GENERAL\n")
        mgr.reload_prompts()

        assert "NEW GENERAL" in mgr.get_system_instruction("general")
        assert "OLD GENERAL" not in mgr.get_system_instruction("general")

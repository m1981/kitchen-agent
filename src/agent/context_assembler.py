"""
src/agent/context_assembler.py
================================
ContextAssembler — makes context window construction explicit and testable.

Before this module, context was assembled implicitly inside the provider's
``process_chat_turn`` method.  This made it impossible to test token budgets,
observe where tokens are being spent, or debug context window issues.

The ContextAssembler has a single responsibility: build the context window.
It knows about budget, ordering, and trimming.  It does NOT know about
LLM providers or tools.

Design decisions
----------------
* **ContextSlot enum**: Every segment of the context window has a named slot.
  This prevents any one segment from starving others and makes token usage
  observable.
* **ContextBudget**: Single place to tune context window allocations.
* **AssembledContext**: Immutable result — what gets handed to the provider.
* **Optional dependencies**: NoteManager and FileManager are optional
  (they arrive in Phase 5).  When absent, those slots are simply empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from src.protocols import (
    FileManagerProtocol,
    NoteManagerProtocol,
    PromptManagerProtocol,
    TokenCounterProtocol,
)


# ---------------------------------------------------------------------------
# Context slot enum
# ---------------------------------------------------------------------------

class ContextSlot(Enum):
    """
    Explicit budget allocation per context segment.
    Prevents any one segment from starving others.
    """

    SYSTEM_PROMPT = auto()
    CONVERSATION_HISTORY = auto()
    ATTACHED_NOTES = auto()
    ATTACHED_FILES = auto()
    SEARCH_RESULTS = auto()
    TOOL_RESULTS = auto()


# ---------------------------------------------------------------------------
# Context budget
# ---------------------------------------------------------------------------

@dataclass
class ContextBudget:
    """
    Token budget per slot.
    Single place to tune context window usage.
    """

    total: int = 128_000
    allocations: dict[ContextSlot, float] = field(default_factory=lambda: {
        ContextSlot.SYSTEM_PROMPT:        0.05,
        ContextSlot.CONVERSATION_HISTORY: 0.35,
        ContextSlot.ATTACHED_NOTES:       0.15,
        ContextSlot.ATTACHED_FILES:       0.15,
        ContextSlot.SEARCH_RESULTS:       0.10,
        ContextSlot.TOOL_RESULTS:         0.20,
    })

    def tokens_for(self, slot: ContextSlot) -> int:
        return int(self.total * self.allocations[slot])


# ---------------------------------------------------------------------------
# Assembled context result
# ---------------------------------------------------------------------------

@dataclass
class AssembledContext:
    """What gets handed to the LLM provider. Immutable after assembly."""

    system_prompt: str
    messages: list[dict]
    total_tokens_estimated: int
    slots_used: dict[ContextSlot, int]  # for observability
    images: list[dict] = field(default_factory=list)  # inline images for the LLM
    context_files: list[str] = field(default_factory=list)  # file paths to inject
    tool_schemas: list[dict] | None = None  # None = tools not requested, [] = no tools available


# Protocols imported from src/protocols.py — single source of truth.
# Re-exported here for backward compatibility.
TokenCounterProtocol = TokenCounterProtocol
PromptManagerProtocol = PromptManagerProtocol
NoteManagerProtocol = NoteManagerProtocol
FileManagerProtocol = FileManagerProtocol


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------

class ContextAssembler:
    """
    Single responsibility: build the context window.

    Knows about budget. Knows about ordering. Knows about trimming.
    Does NOT know about LLM providers or tools.
    """

    def __init__(
        self,
        token_budget: ContextBudget,
        token_counter: TokenCounterProtocol,
        prompt_manager: PromptManagerProtocol,
        note_manager: NoteManagerProtocol | None = None,
        file_manager: FileManagerProtocol | None = None,
    ) -> None:
        self._budget = token_budget
        self._tokens = token_counter
        self._prompts = prompt_manager
        self._notes = note_manager
        self._files = file_manager

    def assemble(
        self,
        session: dict,
        mode: str = "default",
        user_message: str = "",
        note_ids: list[str] | None = None,
        file_ids: list[str] | None = None,
    ) -> AssembledContext:
        """
        Build the full context window for one chat turn.

        Args:
            session:      Session-like dict with a ``messages`` key.
            mode:         Prompt mode (resolved via PromptManager).
            user_message: The user's new message text.
            note_ids:     Optional note IDs to attach.
            file_ids:     Optional file IDs to attach.

        Returns:
            An AssembledContext with system_prompt, messages,
            total_tokens_estimated, and slots_used for observability.
        """
        slots_used: dict[ContextSlot, int] = {}

        system_prompt = self._build_system(mode, slots_used)
        history = self._trim_history(session, slots_used)
        enrichments = self._attach_content(
            session_id=session.get("session_id", ""),
            note_ids=note_ids,
            file_ids=file_ids,
            slots_used=slots_used,
        )

        messages = history + enrichments
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return AssembledContext(
            system_prompt=system_prompt,
            messages=messages,
            tool_schemas=None,
            total_tokens_estimated=sum(slots_used.values()),
            slots_used=slots_used,
        )

    # ── System prompt ────────────────────────────────────────────────

    def _build_system(
        self,
        mode: str,
        slots_used: dict[ContextSlot, int],
    ) -> str:
        prompt = self._prompts.get_system_instruction(mode)
        budget = self._budget.tokens_for(ContextSlot.SYSTEM_PROMPT)
        tokens = self._tokens.count(prompt)

        if tokens > budget:
            prompt = self._tokens.trim_to(prompt, budget)
            tokens = budget

        slots_used[ContextSlot.SYSTEM_PROMPT] = tokens
        return prompt

    # ── History trimming ─────────────────────────────────────────────

    def _trim_history(
        self,
        session: dict,
        slots_used: dict[ContextSlot, int],
    ) -> list[dict]:
        budget = self._budget.tokens_for(ContextSlot.CONVERSATION_HISTORY)
        messages = session.get("messages", [])
        kept: list[dict] = []
        used = 0

        # Walk history newest-first, keep what fits
        for msg in reversed(messages):
            tokens = self._tokens.count_message(msg)
            if used + tokens > budget:
                break
            kept.insert(0, msg)
            used += tokens

        slots_used[ContextSlot.CONVERSATION_HISTORY] = used
        return kept

    # ── Content attachment ───────────────────────────────────────────

    def _attach_content(
        self,
        session_id: str,
        note_ids: list[str] | None,
        file_ids: list[str] | None,
        slots_used: dict[ContextSlot, int],
    ) -> list[dict]:
        """
        Attach notes and files as context messages.
        Each gets its own budget slot — neither starves the other.
        Silently skips if manager not injected (backward compat).
        """
        enrichments: list[dict] = []

        # ── Notes ────────────────────────────────────────────────────────
        if note_ids and self._notes is not None:
            note_budget = self._budget.tokens_for(ContextSlot.ATTACHED_NOTES)
            notes_content = self._notes.get_for_context(
                session_id=session_id,
                max_tokens=note_budget,
            )
            if notes_content:
                enrichments.append({
                    "role": "user",
                    "content": f"<notes>\n{notes_content}\n</notes>",
                })
                slots_used[ContextSlot.ATTACHED_NOTES] = (
                    self._tokens.count(notes_content)
                )

        # ── Files ─────────────────────────────────────────────────────────
        if file_ids and self._files is not None:
            file_budget = self._budget.tokens_for(ContextSlot.ATTACHED_FILES)
            files_content = self._files.get_for_context(
                file_paths=file_ids,
                max_tokens=file_budget,
            )
            if files_content:
                enrichments.append({
                    "role": "user",
                    "content": f"<files>\n{files_content}\n</files>",
                })
                slots_used[ContextSlot.ATTACHED_FILES] = (
                    self._tokens.count(files_content)
                )

        return enrichments

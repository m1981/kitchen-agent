"""
src/prompt_logger.py
====================
Human-readable activity log — the user's "work diary".

Every chat turn is appended to a single Markdown file, grouped by calendar
day, so the user can open it on Friday morning and instantly recall:

  * What they asked the agent
  * Which files the agent read, searched, or edited
  * Exactly what text was added / removed (inline +/- diff)

Design principles
-----------------
* Pure functions — no HTTP, no DB, no FastAPI dependencies.
* ``log_turn()`` is the primary entry point (enriched, with tool data).
* ``log_prompt()`` is kept for backward compatibility — it simply delegates
  to ``log_turn()`` with no tool data.
* The default log path comes from ``settings.prompt_log_path`` so it is
  configurable without touching code.
* Each caller (ChatService) passes its own ``session_id`` and title so the
  log is useful across multiple concurrent sessions.

Entry anatomy
-------------
Each turn produces a block like:

    # 2026-05-30                               ← date banner (once per day)

    ## 14:07 · Session: abc123ef "Zawiasy Blum"  ← turn heading

    > Jakie zawiasy Blum są najlepsze do szafek górnych?

    ### 🛠 Agent actions

    1. 🗺 **get_repo_map** — scanned repo index
    2. 📖 **read_file** — `data/hinges.md`
    3. ✏️  **edit_file** — `data/hinges.md`
       ```diff
       - Zawiasy standardowe
       + Zawiasy Blum Clip Top
       ```

    ---
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings

# Maximum lines shown per diff block before truncation notice is added.
MAX_DIFF_LINES: int = 30

# Sentinel to detect "no date banner written yet" for same-day dedup.
_DATE_BANNER_PREFIX = "# "


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _last_date_in_log(target: Path) -> str | None:
    """
    Returns the most recently written date banner value (e.g. "2026-05-30")
    or None when the file is empty / non-existent.

    We only scan backwards for the first "# YYYY-" pattern to stay O(1) for
    large logs — we read the last 4 KB which is always enough.
    """
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    # Walk lines in reverse to find the most recent date banner
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("# 20") and len(stripped) == 12:
            # "# 2026-05-30" → "2026-05-30"
            return stripped[2:]
    return None


def _render_diff_lines(lines: list[str], prefix: str, max_lines: int) -> list[str]:
    """Renders lines with a +/- prefix, truncating when needed."""
    out: list[str] = []
    for i, line in enumerate(lines):
        if i >= max_lines:
            remaining = len(lines) - max_lines
            out.append(f"   … ({remaining} more lines truncated)")
            break
        out.append(f"   {prefix} {line}")
    return out


def _render_tool(index: int, tool: dict[str, Any]) -> list[str]:
    """
    Renders a single tool call as a numbered Markdown list item, with
    optional diff block for mutating operations.

    Returns a list of lines (without trailing newline).
    """
    name: str = tool.get("name", "unknown")
    args: dict[str, Any] = tool.get("args") or {}
    result: dict[str, Any] = tool.get("result") or {}

    lines: list[str] = []

    # ── get_repo_map ─────────────────────────────────────────────────────────
    if name == "get_repo_map":
        lines.append(f"{index}. 🗺 **get_repo_map** — scanned repo index")

    # ── search_knowledge_base ─────────────────────────────────────────────────
    elif name == "search_knowledge_base":
        query = args.get("query", "")
        lines.append(f"{index}. 🔍 **search_knowledge_base** — `{query}`")

    # ── read_file ─────────────────────────────────────────────────────────────
    elif name == "read_file":
        filepath = args.get("filepath", "?")
        lines.append(f"{index}. 📖 **read_file** — `{filepath}`")

    # ── edit_file ─────────────────────────────────────────────────────────────
    elif name == "edit_file":
        filepath = args.get("filepath", "?")
        if "error" in result:
            lines.append(f"{index}. ✏️ **edit_file** — `{filepath}` ⚠️ FAILED")
            lines.append(f"   > {result['error']}")
        else:
            search_text: str = args.get("search_text", "")
            replace_text: str = args.get("replace_text", "")
            old_lines = search_text.splitlines() if search_text else []
            new_lines = replace_text.splitlines() if replace_text else []

            lines.append(f"{index}. ✏️ **edit_file** — `{filepath}`")
            lines.append("   ```diff")

            # Removed lines
            removed = _render_diff_lines(old_lines, "-", MAX_DIFF_LINES)
            added = _render_diff_lines(new_lines, "+", MAX_DIFF_LINES)
            total = len(removed) + len(added)

            if total > MAX_DIFF_LINES * 2:
                # Both sides exceed — show abbreviated header
                lines.append(f"   … diff truncated ({len(old_lines)} lines removed, {len(new_lines)} lines added)")
            else:
                lines.extend(removed)
                lines.extend(added)

            lines.append("   ```")

    # ── create_file ───────────────────────────────────────────────────────────
    elif name == "create_file":
        filepath = args.get("filepath", "?")
        if "error" in result:
            lines.append(f"{index}. 📄 **create_file** — `{filepath}` ⚠️ FAILED")
            lines.append(f"   > {result['error']}")
        else:
            content_str: str = args.get("content", "")
            content_lines = content_str.splitlines() if content_str else []
            lines.append(f"{index}. 📄 **create_file** — `{filepath}` _(new file)_")
            lines.append("   ```diff")
            rendered = _render_diff_lines(content_lines, "+", MAX_DIFF_LINES)
            lines.extend(rendered)
            lines.append("   ```")

    # ── unknown / future tool ─────────────────────────────────────────────────
    else:
        result_snippet = json.dumps(result)[:120]
        lines.append(f"{index}. ⚙️ **{name}**")
        if args:
            args_snippet = json.dumps(args)[:80]
            lines.append(f"   args: `{args_snippet}`")
        lines.append(f"   result: `{result_snippet}`")

    return lines


def _build_entry(
    user_message: str,
    tool_logs: list[dict[str, Any]] | None,
    now: datetime,
    target: Path,
    session_id: str | None,
    session_title: str | None,
) -> str:
    """
    Builds the full Markdown text for one log entry, including the date
    banner if this is the first entry for today.
    """
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    parts: list[str] = []

    # ── Date banner (once per calendar day) ───────────────────────────────────
    last_date = _last_date_in_log(target)
    if last_date != date_str:
        parts.append(f"# {date_str}\n")

    # ── Turn heading ─────────────────────────────────────────────────────────
    if session_id and session_title:
        short_id = session_id[:8]
        heading = f"## {time_str} · Session: {short_id} \"{session_title}\""
    elif session_id:
        short_id = session_id[:8]
        heading = f"## {time_str} · Session: {short_id}"
    elif session_title:
        heading = f"## {time_str} · \"{session_title}\""
    else:
        heading = f"## {time_str}"

    parts.append(heading)
    parts.append("")

    # ── User message block ────────────────────────────────────────────────────
    # Render as a blockquote to visually separate it from tool output
    for line in user_message.strip().splitlines():
        parts.append(f"> {line}" if line.strip() else ">")
    parts.append("")

    # ── Tool section ──────────────────────────────────────────────────────────
    if tool_logs:
        parts.append("### 🛠 Agent actions")
        parts.append("")
        for i, tool in enumerate(tool_logs, start=1):
            tool_lines = _render_tool(i, tool)
            parts.extend(tool_lines)
        parts.append("")

    # ── Separator ─────────────────────────────────────────────────────────────
    parts.append("---")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_turn(
    user_message: str | None,
    tool_logs: list[dict[str, Any]] | None = None,
    session_id: str | None = None,
    session_title: str | None = None,
    log_path: Path | str | None = None,
) -> None:
    """
    Appends a full human-readable turn entry to the activity log.

    The entry includes:
      * A calendar-day banner the first time a new date is encountered.
      * A turn heading with time (HH:MM) and optional session context.
      * The user's message as a blockquote.
      * A numbered list of every tool call with file paths and inline diffs
        (for edit_file / create_file).

    Empty or whitespace-only messages are silently ignored.

    Args:
        user_message:  The text the user sent this turn.
        tool_logs:     List of tool call dicts produced by the agent:
                       ``[{"name": str, "args": dict, "result": dict}, ...]``
                       May be None or [] when the agent made no tool calls.
        session_id:    Optional session UUID — shown as first 8 chars.
        session_title: Optional human title of the chat session.
        log_path:      Override for the log file path (defaults to
                       ``settings.prompt_log_path``).  Useful in tests.
    """
    if not user_message or not str(user_message).strip():
        return

    target = Path(log_path) if log_path is not None else settings.prompt_log_path
    target.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    entry = _build_entry(
        user_message=str(user_message),
        tool_logs=tool_logs or [],
        now=now,
        target=target,
        session_id=session_id,
        session_title=session_title,
    )

    with target.open("a", encoding="utf-8") as f:
        f.write(entry)


def log_prompt(prompt: str, log_path: Path | str | None = None) -> None:
    """
    Backward-compatible shim — delegates to ``log_turn`` with no tool data.

    Kept so that any code still calling ``log_prompt(...)`` continues to work
    without modification.  New code should call ``log_turn()`` directly.

    Args:
        prompt:   The user prompt to record.
        log_path: Override for the log file path (defaults to
                  ``settings.prompt_log_path``).  Useful in tests.
    """
    log_turn(user_message=prompt, log_path=log_path)

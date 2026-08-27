"""
src/tools/file_ops.py
=====================
File-system tool implementations executed by the agent.

All functions return a plain dict so they can be sent directly back to the
Gemini function-calling API.  Two keys are used:
  {"content":   str}  — success with a string payload
  {"success":   str}  — success with a status message
  {"error":     str}  — failure; the agent will see the reason

Backup / Revert (F03 — API-Native Snapshot Pattern)
----------------------------------------------------
Every mutating tool (edit_file, create_file, append_to_file) optionally
accepts a *backup_dir* keyword argument.  When provided the function:
  1. Saves the pre-mutation state to  backup_dir/.backups/<uuid>.json
  2. Returns  {"revert_id": "<uuid>"}  alongside the normal success key

The caller (FastAPI route in main.py) injects settings.data_dir as
backup_dir, keeping this module decoupled from settings.

Use revert_backup(revert_id, backup_dir) to atomically restore a file.
"""

import difflib
import json
import re
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# The knowledge base root every agent path is resolved against.  Overridden per
# call by the registry, which injects ``settings.data_dir``.
DEFAULT_KB_ROOT = Path("data")

# The knowledge base is markdown-only: these are the extensions get_repo_map
# and search_knowledge_base index, the UI lists, and create_file will write.
# Anything else would exist on disk while being invisible to every part of the
# app — so it is refused rather than silently created.
INDEXED_SUFFIXES = (".md",)


def _resolve_kb_path(filepath: str, base_dir: str | Path | None) -> tuple[Path, str, dict | None]:
    """
    Resolve an agent-supplied path *inside* the knowledge base.

    Returns ``(path, kb_relative_posix, error_dict | None)``.

    With ``base_dir=None`` the path is returned untouched — that is the internal
    contract used by the REST layer and by context-file injection.

    Two things the agent cannot be trusted with are handled here:

    * **Convention.**  ``get_repo_map`` hands the model paths like
      ``data/01_Proces/x.md`` while the REST layer speaks ``01_Proces/x.md``.
      Both are accepted — a leading root segment is stripped — so the model
      cannot land a file outside the KB by dropping or adding the prefix.
    * **Escape.**  Absolute paths and ``..`` traversal are refused instead of
      silently writing wherever the server process happens to be running.
    """
    if base_dir is None:
        # Legacy / internal callers (context-file injection, REST layer, tests)
        # pass paths that are already resolved against their own root.  The jail
        # applies to agent-supplied paths, which arrive with base_dir bound by
        # the tool registry.
        legacy = Path(filepath)
        return legacy, legacy.as_posix(), None

    root = Path(base_dir)
    root_resolved = root.resolve()
    raw = (filepath or "").strip()

    if not raw:
        return root, "", {"error": "filepath is empty."}

    candidate = Path(raw)
    if candidate.is_absolute():
        return root, "", {
            "error": (
                f"Absolute paths are not allowed: {raw!r}. "
                f"Use a path relative to the knowledge base root ({root.as_posix()}/), "
                "e.g. '01_Proces/notes.md'."
            )
        }

    # Tolerate the 'data/' prefix the discovery tools emit.
    parts = candidate.parts
    if parts and parts[0] == root.name:
        candidate = Path(*parts[1:]) if len(parts) > 1 else Path()

    target = (root / candidate).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        return root, "", {
            "error": (
                f"Path escapes the knowledge base: {raw!r}. "
                f"Everything must stay under {root.as_posix()}/."
            )
        }

    return target, target.relative_to(root_resolved).as_posix(), None


_LINE_NUMBER_PREFIX = re.compile(r"^\s*\d+:\s?")


def _strip_line_numbers(text: str) -> str:
    """
    Drop the ``N: `` prefixes that read_file adds for display.

    Only when *every* non-empty line carries one — otherwise the text is taken
    literally, so a document that genuinely starts lines with digits and a
    colon is never mangled.
    """
    lines = text.split("\n")
    meaningful = [ln for ln in lines if ln.strip()]
    if not meaningful or not all(_LINE_NUMBER_PREFIX.match(ln) for ln in meaningful):
        return text
    return "\n".join(_LINE_NUMBER_PREFIX.sub("", ln) if ln.strip() else ln for ln in lines)


def _render_diff(before: str, after: str, label: str, max_lines: int = 40) -> str:
    """Unified diff of what actually changed — the model's only feedback loop."""
    diff = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"{label} (before)", tofile=f"{label} (after)",
        lineterm="", n=2,
    ))
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"... ({len(diff) - max_lines} more diff lines)"]
    return "\n".join(diff)


def _read_path(filepath: str, base_dir: str | Path | None = None) -> tuple[Path, dict | None]:
    """
    Returns (resolved_path, None) on success, or (path, error_dict) when the
    file does not exist.  Callers return the error_dict immediately.
    """
    p, kb_rel, err = _resolve_kb_path(filepath, base_dir)
    if err:
        return p, err
    if not p.exists():
        return p, {"error": f"File not found: {kb_rel or filepath}"}
    return p, None


# ---------------------------------------------------------------------------
# F03 — Backup / Snapshot helpers
# ---------------------------------------------------------------------------

def _create_backup(target_path: Path, backup_dir: Path) -> str:
    """
    Saves the *current* state of *target_path* into
    ``backup_dir/.backups/<uuid>.json`` and returns the revert_id (UUID string).

    The JSON envelope contains:
      - filepath : str    — posix path of the target file (as stored, not resolved)
      - existed  : bool   — whether the file existed at snapshot time
      - content  : str|None — full text content, or None when the file didn't exist

    Design decisions:
      - filepath is stored as-is (posix) so it survives cross-platform moves.
      - The backup_dir is always injected by the caller; this function has no
        dependency on ``settings`` and is therefore trivially unit-testable.
    """
    backup_id = str(uuid.uuid4())
    backup_folder = backup_dir / ".backups"
    backup_folder.mkdir(parents=True, exist_ok=True)

    state = {
        "filepath": target_path.as_posix(),
        "existed": target_path.exists(),
        "content": (
            target_path.read_text(encoding="utf-8") if target_path.exists() else None
        ),
    }

    (backup_folder / f"{backup_id}.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    return backup_id


def revert_backup(revert_id: str, backup_dir: Path) -> dict:
    """
    Reads the backup snapshot identified by *revert_id* and restores the file.

    Behaviour:
      - existed=True  → write original content back to the file
      - existed=False → delete the file (it was created by the agent)
      - If the file to delete is already gone, that is treated as a no-op
        (idempotent success) because the end-state is correct.

    Cleanup:
      - The backup JSON is deleted ONLY after a successful restore so that a
        failed restore (e.g. disk full) can still be retried.

    Returns:
      {"success": True, "message": str}  on success
      {"error": str}                      on failure (never raises)
    """
    backup_file = backup_dir / ".backups" / f"{revert_id}.json"

    if not backup_file.exists():
        return {"error": f"Backup not found or already reverted: {revert_id}"}

    # --- Parse backup JSON ---------------------------------------------------
    try:
        state = json.loads(backup_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"error": f"Backup file is malformed or unreadable: {exc}"}

    target_path = Path(state["filepath"])
    existed: bool = state["existed"]
    content: str | None = state["content"]

    # --- Restore -------------------------------------------------------------
    try:
        if existed:
            # Restore original content (covers edit_file and append_to_file)
            target_path.write_text(content or "", encoding="utf-8")
        else:
            # The file was created by the agent — reverting means deleting it
            if target_path.exists():
                target_path.unlink()
            # If already gone: no-op; the desired post-revert state is met
    except OSError as exc:
        return {"error": f"Failed to restore {target_path.name}: {exc}"}

    # --- Clean up backup (only on success) -----------------------------------
    try:
        backup_file.unlink()
    except OSError:
        pass  # Best-effort cleanup; not fatal

    return {
        "success": True,
        "message": f"Reverted changes to {target_path.name}",
    }


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

# Lines returned by one read_file call when the model asks for no window.
# A whole 20 KB document is ~6k tokens — a quarter of the tool-result budget
# for the entire turn — and once the budget truncates it the model silently
# edits against text whose end it never saw.
DEFAULT_READ_LIMIT = 300


def read_file(
    filepath: str,
    base_dir: str | Path | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    """
    Read a file as **numbered lines**, optionally a window of them.

    ``offset`` is 1-based and inclusive; ``limit`` counts lines.  The numbers
    are what the model cites, and the header states exactly which slice it is
    looking at so a partial read can never pass for the whole file.

    The ``N: `` prefix is presentation only — ``edit_file`` strips it if the
    model pastes it back, but the model is told not to.
    """
    p, err = _read_path(filepath, base_dir)
    if err:
        return err
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}

    if base_dir is None:
        # Internal callers (context-file injection, REST layer) want the file
        # verbatim — numbering and windowing are for the agent's read path,
        # which is the one that carries a bound knowledge base root.
        return {"content": text}

    lines = text.splitlines()
    total = len(lines)

    try:
        start = max(1, int(offset)) if offset is not None else 1
        count = max(1, int(limit)) if limit is not None else DEFAULT_READ_LIMIT
    except (TypeError, ValueError):
        return {"error": "offset and limit must be integers."}

    if total and start > total:
        return {"error": f"offset {start} is past the end of the file ({total} lines)."}

    window = lines[start - 1: start - 1 + count]
    end = start + len(window) - 1
    numbered = "\n".join(f"{n}: {line}" for n, line in enumerate(window, start=start))

    kb_rel = _resolve_kb_path(filepath, base_dir)[1]
    if start == 1 and end >= total:
        header = f"[{kb_rel} — complete file, {total} line(s)]"
    else:
        header = (
            f"[{kb_rel} — lines {start}-{end} of {total}. "
            f"Call read_file again with offset={end + 1} for the rest.]"
        )

    return {"content": f"{header}\n{numbered}" if numbered else header}


def edit_file(
    filepath: str,
    search_text: str,
    replace_text: str,
    backup_dir: Path | None = None,
    base_dir: str | Path | None = None,
) -> dict:
    """
    Safely edits a file using exact search-and-replace.

    Returns an error when *search_text* is not found so the agent can
    re-read the file before trying again — preventing accidental data loss.

    When *backup_dir* is provided the pre-edit state is snapshotted and the
    response includes a ``revert_id`` key that the frontend can use to undo
    the change.
    """
    p, kb_rel, err = _resolve_kb_path(filepath, base_dir)
    if err:
        return err
    if not p.exists():
        return {"error": f"File not found: {kb_rel}"}
    try:
        content = p.read_text(encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}

    effective_search = search_text
    effective_replace = replace_text
    if effective_search not in content:
        # The model pasted back what read_file displayed, line numbers included.
        stripped_search = _strip_line_numbers(search_text)
        if stripped_search != search_text and stripped_search in content:
            effective_search = stripped_search
            effective_replace = _strip_line_numbers(replace_text)

    if effective_search not in content:
        return {
            "error": (
                "Search text not found in file. Read the file again and copy the "
                "exact current text — without the 'N: ' line-number prefix, which "
                "is display only."
            )
        }

    # Snapshot BEFORE mutating (only when a backup destination is provided)
    revert_id: str | None = None
    if backup_dir is not None:
        revert_id = _create_backup(target_path=p, backup_dir=backup_dir)

    occurrences = content.count(effective_search)
    updated = content.replace(effective_search, effective_replace)
    p.write_text(updated, encoding="utf-8")

    # Report the resolved path, never the model's own input: a confirmation
    # that echoes a wrong path is what makes a lost edit look like a done one.
    result: dict = {
        "success": (
            f"Updated {kb_rel} — replaced {occurrences} occurrence(s), "
            f"file is now {p.stat().st_size} bytes."
        )
    }
    # What changed, not what was asked for — the model cannot otherwise tell a
    # whitespace-off edit from the one it intended.
    result["diff"] = _render_diff(content, updated, kb_rel)
    if occurrences > 1:
        result["warning"] = (
            f"search_text matched {occurrences} times and every match was replaced. "
            "Use a longer, unique excerpt if you meant to change only one."
        )
    if revert_id is not None:
        result["revert_id"] = revert_id
    return result


def create_file(
    filepath: str,
    content: str,
    backup_dir: Path | None = None,
    base_dir: str | Path | None = None,
) -> dict:
    """
    Creates a new file with the given content.

    Refuses to overwrite an existing file — the agent must use edit_file
    for updates — and refuses any extension outside INDEXED_SUFFIXES, which
    would land on disk without ever showing up in search or the file browser.

    When *backup_dir* is provided a snapshot is taken (recording that the
    file did not exist) so the creation can be reverted by deleting the file.
    """
    p, kb_rel, err = _resolve_kb_path(filepath, base_dir)
    if err:
        return err
    if p.suffix.lower() not in INDEXED_SUFFIXES:
        return {
            "error": (
                f"Only {', '.join(INDEXED_SUFFIXES)} files can be created: "
                f"{kb_rel or filepath} was refused. get_repo_map, "
                "search_knowledge_base and the file browser index markdown only, "
                "so another format would be invisible to you and to the user. "
                "Write the document as markdown instead."
            )
        }
    if p.exists():
        return {"error": f"File already exists at {kb_rel}. Use edit_file instead."}

    root = Path(base_dir) if base_dir is not None else DEFAULT_KB_ROOT

    # Snapshot BEFORE creating (records existed=False)
    revert_id: str | None = None
    if backup_dir is not None:
        revert_id = _create_backup(target_path=p, backup_dir=backup_dir)

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}

    result: dict = {
        "success": f"Created {kb_rel} ({len(content.encode('utf-8'))} bytes)."
    }

    # A copy of the same document elsewhere is the usual cause of "the model
    # says it wrote the file and I cannot find it" — say so straight away.
    duplicates = [
        other.relative_to(root.resolve()).as_posix()
        for other in root.resolve().rglob(p.name)
        if other != p
    ]
    if duplicates:
        result["warning"] = (
            f"A file named {p.name} already exists at: {', '.join(duplicates[:5])}. "
            "Check whether you meant to edit one of those instead."
        )

    if revert_id is not None:
        result["revert_id"] = revert_id
    return result


def append_to_file(
    filepath: str,
    content: str,
    backup_dir: Path | None = None,
) -> dict:
    """
    Appends *content* to an existing file (or creates it when absent).

    Used by the UI's "Highlight → Add to Docs" feature and exposed as a
    REST endpoint; NOT exposed to the LLM as a tool.

    When *backup_dir* is provided the pre-append state is snapshotted
    (or the non-existence of the file is recorded) for revert support.
    """
    p = Path(filepath)

    # Snapshot BEFORE mutating (backup_dir opt-in)
    revert_id: str | None = None
    if backup_dir is not None:
        revert_id = _create_backup(target_path=p, backup_dir=backup_dir)

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            # Ensure a blank line separates existing content from the snippet.
            f.write("\n" + content)
    except OSError as exc:
        return {"error": str(exc)}

    result: dict = {"success": f"Successfully appended to {filepath}."}
    if revert_id is not None:
        result["revert_id"] = revert_id
    return result


def search_knowledge_base(
    query: str,
    base_dir: str = "data",
    context_lines: int = 2,
) -> dict:
    """
    Searches all Markdown files under *base_dir* for lines matching a
    case-insensitive regex pattern.

    Supports OR logic via the pipe character, e.g. ``'hinge|blum|runner'``.

    Args:
        query:         Regex pattern (case-insensitive).  Pipe = OR logic.
        base_dir:      Root directory to scan.  Fixed by the registry lambda.
        context_lines: Number of lines to include BEFORE and AFTER each match.
                       Default 2 gives the model enough surrounding text to
                       resolve contradictions across files without loading whole
                       files.  Pass 0 for the legacy single-line behaviour.

    Returns up to MAX_MATCHES *match groups* (each group = context window).
    When context windows from the same file overlap they are merged into one
    contiguous block to avoid duplication.
    """
    MAX_MATCHES = 200

    base_path = Path(base_dir)
    if not base_path.exists():
        return {"error": f"Directory not found: {base_dir}"}

    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as exc:
        return {"error": f"Invalid regex pattern: {exc}"}

    output_blocks: list[str] = []   # final rendered blocks, one per file section
    total_match_count = 0
    truncated = False

    for filepath in sorted(base_path.rglob("*.md")):
        try:
            lines = filepath.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        # ── Collect 0-based indices of matching lines ─────────────────────
        hit_indices: list[int] = []
        for idx, line in enumerate(lines):
            if pattern.search(line):
                hit_indices.append(idx)
                total_match_count += 1
                if total_match_count >= MAX_MATCHES:
                    truncated = True
                    break

        if not hit_indices:
            continue

        if context_lines == 0:
            # ── Legacy behaviour: one line per match ──────────────────────
            file_header = f"=== {filepath.as_posix()} ==="
            file_lines: list[str] = [file_header]
            for idx in hit_indices:
                line_num = idx + 1
                file_lines.append(f"{line_num}: {lines[idx]}")
            output_blocks.append("\n".join(file_lines))
        else:
            # ── Context mode: merge overlapping windows ───────────────────
            # Build contiguous intervals [start, end] (inclusive, 0-based)
            intervals: list[tuple[int, int]] = []
            n = len(lines)
            for idx in hit_indices:
                start = max(0, idx - context_lines)
                end = min(n - 1, idx + context_lines)
                if intervals and start <= intervals[-1][1] + 1:
                    # Overlaps or adjacent — extend the previous interval
                    intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))
                else:
                    intervals.append((start, end))

            file_header = f"=== {filepath.as_posix()} ==="
            file_lines = [file_header]
            for seg_idx, (start, end) in enumerate(intervals):
                if seg_idx > 0:
                    file_lines.append("---")  # separator between non-adjacent windows
                for i in range(start, end + 1):
                    line_num = i + 1
                    marker = ">>" if pattern.search(lines[i]) else "  "
                    file_lines.append(f"{marker} {line_num}: {lines[i]}")
            output_blocks.append("\n".join(file_lines))

        if truncated:
            break

    if not output_blocks:
        return {"content": f"No matches found for pattern: '{query}'"}

    result_text = "\n\n".join(output_blocks)
    if truncated:
        result_text += f"\n\n... (truncated at {MAX_MATCHES} matches)"

    return {"content": result_text}

"""
src/tools/repo_map.py
=====================
Lightweight "repo map" tool: scans the knowledge-base directory for Markdown
files and extracts their headings so the LLM can decide which file to read
without loading the full content of every file.
"""

from pathlib import Path


def get_repo_map(base_dir: str = "data", max_files: int = 30, max_chars: int = 8000) -> dict:
    """
    Scans *base_dir* recursively for ``.md`` files and extracts their Markdown
    headings (lines starting with ``#``).

    Args:
        base_dir:  Root directory to scan.
        max_files: Maximum number of files to include (prevents context overflow).
        max_chars: Maximum total output size in characters.

    Returns:
        {"content": str}  — formatted map ready for the model.
        {"error":   str}  — when *base_dir* does not exist.
    """
    base_path = Path(base_dir)
    if not base_path.exists():
        return {"error": f"Directory not found: {base_dir}"}

    output: list[str] = []
    file_count = 0
    total_chars = 0
    truncated = False

    for filepath in sorted(base_path.rglob("*.md")):
        if file_count >= max_files:
            truncated = True
            break

        # Full POSIX path so the LLM can pass it directly to read_file.
        header = f"\n=== {filepath.as_posix()} ==="
        lines: list[str] = [header]
        try:
            for line_num, line in enumerate(
                filepath.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.startswith("#"):
                    lines.append(f"{line_num}: {line.strip()}")
        except OSError:
            lines.append("  (unreadable)")

        file_block = "\n".join(lines)
        if total_chars + len(file_block) > max_chars:
            truncated = True
            break

        output.append(file_block)
        total_chars += len(file_block)
        file_count += 1

    if not output:
        return {"content": "No markdown files found."}

    result = "\n".join(output)
    if truncated:
        result += f"\n\n... (showing {file_count} files, {len(list(base_path.rglob('*.md')))} total. Use search_knowledge_base to find specific topics.)"

    return {"content": result}

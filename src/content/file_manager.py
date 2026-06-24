"""
src/content/file_manager.py
=============================
FileManager — domain logic for file context assembly.

Sits between the service layer and file operations.
Provides:
  - Read file content for LLM context window
  - Token-budget-aware file injection
  - Batch file reading with budget enforcement

Phase 5 scope: basic file reading + context assembly.
"""
from __future__ import annotations

from src.protocols import TokenCounterProtocol


# ---------------------------------------------------------------------------
# FileManager
# ---------------------------------------------------------------------------

class FileManager:
    """
    Domain logic for file context assembly.

    Responsibilities:
    - Read files and format for LLM context window
    - Enforce token budgets on file content
    - Batch multiple files within a shared budget

    Does NOT know about HTTP, schemas, or backup logic.
    """

    def __init__(
        self,
        token_counter: TokenCounterProtocol | None = None,
        data_dir: str = "data",
    ) -> None:
        self._tokens = token_counter
        self._data_dir = data_dir

    def get_for_context(
        self,
        file_paths: list[str],
        max_tokens: int = 4000,
    ) -> str:
        """
        Read files and format for LLM context window.

        Respects token budget — if files exceed the budget, later files
        are truncated or skipped.

        Args:
            file_paths: List of file paths to read.
            max_tokens: Maximum tokens to use for all files combined.

        Returns:
            Formatted string of file contents, or empty string if no files.
        """
        if not file_paths:
            return ""

        from src.tools.file_ops import read_file

        parts: list[str] = []
        tokens_used = 0

        for fp in file_paths:
            result = read_file(fp)
            if "error" in result:
                continue

            content = result.get("content", "")
            if not content:
                continue

            header = f"=== {fp} ==="
            full_block = f"{header}\n{content}"

            # Check budget
            if self._tokens:
                block_tokens = self._tokens.count(full_block)
                remaining = max_tokens - tokens_used

                if remaining <= 0:
                    break

                if block_tokens > remaining:
                    # Trim content to fit (leave room for header)
                    header_tokens = self._tokens.count(header + "\n")
                    content_budget = remaining - header_tokens - 2  # 2 for newlines
                    if content_budget <= 0:
                        break
                    content = self._tokens.trim_to(content, content_budget)
                    full_block = f"{header}\n{content}"
                    block_tokens = self._tokens.count(full_block)

                tokens_used += block_tokens

            parts.append(full_block)

        return "\n\n".join(parts)

    def read_file(self, filepath: str) -> dict:
        """
        Read a single file.

        Returns:
            {"content": str} on success, {"error": str} on failure.
        """
        from src.tools.file_ops import read_file
        return read_file(filepath)

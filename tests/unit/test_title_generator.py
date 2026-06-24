"""
tests/unit/test_title_generator.py
===================================
Unit tests for shared title derivation logic.

Tests the single source of truth used by ChatService and ImportService.
"""

from src.title_generator import derive_title


class TestDeriveTitle:
    """Test suite for derive_title() function."""

    def test_short_user_message_returned_as_is(self) -> None:
        """Short user message is returned without truncation."""
        msgs = [{"role": "user", "content": "Hello"}]
        assert derive_title(msgs) == "Hello"

    def test_long_user_message_truncated(self) -> None:
        """Long user message is truncated to max_len + '...'."""
        msgs = [{"role": "user", "content": "A" * 40}]
        title = derive_title(msgs)
        assert title.endswith("...")
        assert len(title) == 33  # 30 chars + "..."

    def test_exact_max_len_not_truncated(self) -> None:
        """Message exactly at max_len is NOT truncated."""
        msgs = [{"role": "user", "content": "A" * 30}]
        assert derive_title(msgs) == "A" * 30

    def test_custom_max_len(self) -> None:
        """Custom max_len parameter is respected."""
        msgs = [{"role": "user", "content": "Hello World"}]
        assert derive_title(msgs, max_len=5) == "Hello..."

    def test_no_user_message_returns_default(self) -> None:
        """Returns 'New Chat' when no user message exists."""
        msgs = [{"role": "assistant", "content": "Hi"}]
        assert derive_title(msgs) == "New Chat"

    def test_empty_list_returns_default(self) -> None:
        """Returns 'New Chat' for empty message list."""
        assert derive_title([]) == "New Chat"

    def test_first_user_message_used(self) -> None:
        """Uses the FIRST user message, not subsequent ones."""
        msgs = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Second"},
        ]
        assert derive_title(msgs) == "First"

    def test_missing_content_key_skipped(self) -> None:
        """Messages without 'content' key are skipped."""
        msgs = [
            {"role": "user"},  # No content key
            {"role": "user", "content": "Valid message"},
        ]
        assert derive_title(msgs) == "Valid message"

    def test_missing_role_key_skipped(self) -> None:
        """Messages without 'role' key are skipped."""
        msgs = [
            {"content": "No role"},
            {"role": "user", "content": "Valid message"},
        ]
        assert derive_title(msgs) == "Valid message"

    def test_whitespace_only_content_preserved(self) -> None:
        """Whitespace-only content is valid (not treated as empty)."""
        msgs = [{"role": "user", "content": "   "}]
        assert derive_title(msgs) == "   "

    def test_multiline_content_truncated(self) -> None:
        """Multiline content is truncated correctly."""
        msgs = [{"role": "user", "content": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"}]
        title = derive_title(msgs, max_len=10)
        assert title == "Line 1\nLin..."

    def test_unicode_content_handled(self) -> None:
        """Unicode content is handled correctly."""
        msgs = [{"role": "user", "content": "Kuchnie z klasą 🍳"}]
        assert derive_title(msgs) == "Kuchnie z klasą 🍳"

    def test_provider_model_fields_ignored(self) -> None:
        """Extra fields like provider/model don't affect title extraction."""
        msgs = [
            {
                "role": "user",
                "content": "Hello",
                "provider": "openai",
                "model": "gpt-4",
            }
        ]
        assert derive_title(msgs) == "Hello"

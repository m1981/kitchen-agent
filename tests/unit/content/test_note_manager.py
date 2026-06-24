"""
tests/unit/content/test_note_manager.py
=========================================
Unit tests for NoteManager — domain logic for notes.

The NoteManager provides:
  - CRUD operations with validation
  - Context assembly (notes formatted for LLM context window)
  - Search delegation to SearchCoordinator

These tests use fakes — no real database or search backends.
"""
import pytest

from src.content.note_manager import Note, NoteManager


# ---------------------------------------------------------------------------
# Fakes for isolated testing
# ---------------------------------------------------------------------------

class FakeNoteRepository:
    """In-memory note store for testing."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._next_id = 1

    def add_note(
        self,
        session_id: str,
        selected_text: str,
        source_role: str,
        note: str = "",
    ) -> dict:
        note_id = f"note-{self._next_id}"
        self._next_id += 1
        entry = {
            "id": note_id,
            "session_id": session_id,
            "selected_text": selected_text,
            "note": note,
            "source_role": source_role,
            "created_at": "2026-01-01T00:00:00",
        }
        self._store[note_id] = entry
        return entry

    def list_notes(self, session_id: str) -> list[dict]:
        return [
            n for n in self._store.values()
            if n["session_id"] == session_id
        ]

    def delete_note(self, note_id: str, session_id: str) -> bool:
        key = note_id
        if key in self._store and self._store[key]["session_id"] == session_id:
            del self._store[key]
            return True
        return False


class FakeTokenCounter:
    """Predictable token counter: 1 token per 4 characters."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def trim_to(self, text: str, max_tokens: int) -> str:
        return text[: max_tokens * 4]


class FakeSearchCoordinator:
    """Controllable search coordinator for testing."""

    def __init__(self, results: list | None = None) -> None:
        self._results = results or []
        self.search_queries: list[str] = []

    def search(
        self,
        query: str,
        limit: int = 10,
        backends: list[str] | None = None,
    ) -> list:
        self.search_queries.append(query)
        return self._results[:limit]

    def was_called_with_query(self, query: str) -> bool:
        return query in self.search_queries


# ---------------------------------------------------------------------------
# Tests: NoteManager — create
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_returns_note(self):
        manager = NoteManager(repo=FakeNoteRepository())

        note = manager.create(
            session_id="sess-1",
            selected_text="Important text",
            source_role="user",
        )

        assert isinstance(note, Note)
        assert note.id is not None
        assert note.selected_text == "Important text"
        assert note.source_role == "user"

    def test_create_with_annotation(self):
        manager = NoteManager(repo=FakeNoteRepository())

        note = manager.create(
            session_id="sess-1",
            selected_text="Text",
            source_role="assistant",
            note="Remember this",
        )

        assert note.note == "Remember this"

    def test_create_empty_text_raises(self):
        manager = NoteManager(repo=FakeNoteRepository())

        with pytest.raises(ValueError, match="must not be empty"):
            manager.create(
                session_id="sess-1",
                selected_text="",
                source_role="user",
            )

    def test_create_whitespace_only_text_raises(self):
        manager = NoteManager(repo=FakeNoteRepository())

        with pytest.raises(ValueError, match="must not be empty"):
            manager.create(
                session_id="sess-1",
                selected_text="   ",
                source_role="user",
            )

    def test_create_persists_in_repo(self):
        repo = FakeNoteRepository()
        manager = NoteManager(repo=repo)

        note = manager.create(
            session_id="sess-1",
            selected_text="Persisted",
            source_role="user",
        )

        assert note.id in repo._store


# ---------------------------------------------------------------------------
# Tests: NoteManager — list_notes
# ---------------------------------------------------------------------------

class TestListNotes:
    def test_empty_list_for_session_with_no_notes(self):
        manager = NoteManager(repo=FakeNoteRepository())

        notes = manager.list_notes("sess-empty")

        assert notes == []

    def test_returns_notes_for_session(self):
        manager = NoteManager(repo=FakeNoteRepository())
        manager.create("sess-1", "Text 1", "user")
        manager.create("sess-1", "Text 2", "assistant")

        notes = manager.list_notes("sess-1")

        assert len(notes) == 2
        assert all(isinstance(n, Note) for n in notes)

    def test_notes_isolated_between_sessions(self):
        manager = NoteManager(repo=FakeNoteRepository())
        manager.create("sess-1", "Text A", "user")
        manager.create("sess-2", "Text B", "user")

        notes_1 = manager.list_notes("sess-1")
        notes_2 = manager.list_notes("sess-2")

        assert len(notes_1) == 1
        assert len(notes_2) == 1
        assert notes_1[0].selected_text == "Text A"
        assert notes_2[0].selected_text == "Text B"


# ---------------------------------------------------------------------------
# Tests: NoteManager — delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_returns_true_when_found(self):
        manager = NoteManager(repo=FakeNoteRepository())
        note = manager.create("sess-1", "Text", "user")

        result = manager.delete(note.id, "sess-1")

        assert result is True

    def test_delete_returns_false_when_not_found(self):
        manager = NoteManager(repo=FakeNoteRepository())

        result = manager.delete("nonexistent", "sess-1")

        assert result is False

    def test_delete_removes_from_list(self):
        manager = NoteManager(repo=FakeNoteRepository())
        note = manager.create("sess-1", "Text", "user")

        manager.delete(note.id, "sess-1")
        notes = manager.list_notes("sess-1")

        assert len(notes) == 0


# ---------------------------------------------------------------------------
# Tests: NoteManager — get_for_context
# ---------------------------------------------------------------------------

class TestGetForContext:
    def test_empty_notes_returns_empty_string(self):
        manager = NoteManager(repo=FakeNoteRepository())

        result = manager.get_for_context("sess-empty")

        assert result == ""

    def test_notes_formatted_as_string(self):
        manager = NoteManager(repo=FakeNoteRepository())
        manager.create("sess-1", "Important text", "user", note="Note")

        result = manager.get_for_context("sess-1")

        assert "Important text" in result
        assert "user" in result

    def test_respects_token_budget(self):
        # Long content that exceeds budget
        long_text = "word " * 1000  # ~125 tokens with our counter
        repo = FakeNoteRepository()
        manager = NoteManager(repo=repo, token_counter=FakeTokenCounter())
        manager.create("sess-1", long_text, "user")

        result = manager.get_for_context("sess-1", max_tokens=50)

        # Should be trimmed
        tokens = FakeTokenCounter().count(result)
        assert tokens <= 60  # some overhead for formatting

    def test_multiple_notes_all_included(self):
        manager = NoteManager(repo=FakeNoteRepository())
        manager.create("sess-1", "Text 1", "user")
        manager.create("sess-1", "Text 2", "assistant")

        result = manager.get_for_context("sess-1")

        assert "Text 1" in result
        assert "Text 2" in result


# ---------------------------------------------------------------------------
# Tests: NoteManager — search delegation
# ---------------------------------------------------------------------------

class TestSearchDelegation:
    def test_search_delegates_to_coordinator(self):
        from src.content.search_coordinator import SearchResult

        search = FakeSearchCoordinator(results=[
            SearchResult(
                source="bm25",
                content="Q4 roadmap discussion",
                score=0.95,
            )
        ])
        manager = NoteManager(repo=FakeNoteRepository(), search=search)

        results = manager.search("Q4 roadmap")

        assert len(results) == 1
        assert search.was_called_with_query("Q4 roadmap")

    def test_search_without_coordinator_returns_empty(self):
        manager = NoteManager(repo=FakeNoteRepository())

        results = manager.search("query")

        assert results == []


# ---------------------------------------------------------------------------
# Tests: Note dataclass
# ---------------------------------------------------------------------------

class TestNoteDataclass:
    def test_fields(self):
        note = Note(
            id="n1",
            session_id="s1",
            selected_text="text",
            note="annotation",
            source_role="user",
            created_at="2026-01-01",
        )
        assert note.id == "n1"
        assert note.session_id == "s1"
        assert note.selected_text == "text"
        assert note.note == "annotation"
        assert note.source_role == "user"
        assert note.created_at == "2026-01-01"

    def test_defaults(self):
        note = Note(id="n1", session_id="s1", selected_text="text")
        assert note.note == ""
        assert note.source_role == ""
        assert note.created_at == ""

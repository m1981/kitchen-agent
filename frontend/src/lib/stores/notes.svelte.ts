/**
 * src/lib/stores/notes.svelte.ts
 * ================================
 * Rune-based store for per-session notes.
 *
 * Notes are keyed by session ID so switching sessions is instant — no
 * refetch needed if already loaded.  The store exposes `forSession(id)`
 * which returns the live reactive array (or [] before first load).
 *
 * Deletes are optimistic: the note disappears immediately and rolls back
 * only if the DELETE request fails.
 */

import { api, type Note, type NoteCreateRequest } from "$lib/api";
import type { AsyncState } from "$lib/types";

function createNotesStore() {
  // bySession[sessionId] = reactive Note[]
  let bySession = $state<Record<string, Note[]>>({});
  // track per-session fetch status
  let fetchStates = $state<Record<string, AsyncState<Note[]>>>({});

  return {
    // ── Reads ────────────────────────────────────────────────────────────

    /** Live reactive list of notes for a session. Returns [] before load. */
    forSession(sessionId: string): Note[] {
      return bySession[sessionId] ?? [];
    },

    fetchStateFor(sessionId: string): AsyncState<Note[]> {
      return fetchStates[sessionId] ?? { status: "idle" };
    },

    // ── Mutations ────────────────────────────────────────────────────────

    async load(sessionId: string) {
      // Don't re-fetch if already loaded — caller can use refresh() to force.
      const current = fetchStates[sessionId]?.status;
      if (current === "loading" || current === "success") return;

      fetchStates = { ...fetchStates, [sessionId]: { status: "loading" } };
      try {
        const notes = await api.getNotes(sessionId);
        bySession = { ...bySession, [sessionId]: notes };
        fetchStates = { ...fetchStates, [sessionId]: { status: "success", data: notes } };
      } catch (e) {
        fetchStates = {
          ...fetchStates,
          [sessionId]: { status: "error", message: String(e) },
        };
      }
    },

    async refresh(sessionId: string) {
      fetchStates = {
        ...fetchStates,
        [sessionId]: { status: "loading" },
      };
      try {
        const notes = await api.getNotes(sessionId);
        bySession = { ...bySession, [sessionId]: notes };
        fetchStates = { ...fetchStates, [sessionId]: { status: "success", data: notes } };
      } catch (e) {
        fetchStates = {
          ...fetchStates,
          [sessionId]: { status: "error", message: String(e) },
        };
      }
    },

    async create(sessionId: string, payload: NoteCreateRequest): Promise<Note> {
      const note = await api.createNote(sessionId, payload);
      // Append to local list immediately (optimistic-style append).
      bySession = {
        ...bySession,
        [sessionId]: [...(bySession[sessionId] ?? []), note],
      };
      return note;
    },

    async delete(sessionId: string, noteId: string) {
      // Optimistic removal.
      const prev = bySession[sessionId] ?? [];
      bySession = {
        ...bySession,
        [sessionId]: prev.filter((n) => n.id !== noteId),
      };
      try {
        await api.deleteNote(sessionId, noteId);
      } catch (e) {
        // Rollback.
        bySession = { ...bySession, [sessionId]: prev };
        throw e;
      }
    },
  };
}

// Singleton.
export const notesStore = createNotesStore();

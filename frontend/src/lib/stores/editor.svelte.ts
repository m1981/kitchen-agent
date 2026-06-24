/**
 * lib/stores/editor.svelte.ts
 * =============================
 * Rune-based store for message editing and system prompt editing.
 *
 * Responsibilities:
 *   - Inline message editing (start, cancel, save, draft)
 *   - Message deletion (single, pair-delete)
 *   - Turn truncation
 *   - System prompt editor (open, close, save, clear)
 *
 * Cross-store reads (passed as args, not imported):
 *   - sessionId (from chatMessagingStore)
 *   - messages (from chatMessagingStore)
 */

import { api, type Message } from "$lib/api";
import type { AsyncState } from "$lib/types";

function createEditorStore() {
  // ── Message editor ────────────────────────────────────────────────────
  let editingTurnId = $state<string | null>(null);
  let editDraft = $state<string>("");
  let editState = $state<AsyncState<void>>({ status: "idle" });

  // ── System prompt ─────────────────────────────────────────────────
  let sessionSystemPrompt = $state<string | null>(null);
  let modeDefaultPrompt = $state<string>("");
  let systemPromptDraft = $state<string>("");
  let systemPromptState = $state<AsyncState<void>>({ status: "idle" });

  return {
    // Message editor
    get editingTurnId() {
      return editingTurnId;
    },
    get editDraft() {
      return editDraft;
    },
    get editState() {
      return editState;
    },

    // System prompt
    get sessionSystemPrompt() {
      return sessionSystemPrompt;
    },
    get modeDefaultPrompt() {
      return modeDefaultPrompt;
    },
    /** Resolved text: session override ?? mode default */
    get resolvedSystemPrompt() {
      return sessionSystemPrompt ?? modeDefaultPrompt;
    },
    /**
     * Whether the displayed text is a session-specific override.
     * An override is only active when the saved prompt is non-null,
     * non-empty, AND differs from the mode default.
     */
    get isSystemPromptOverride() {
      if (sessionSystemPrompt === null || sessionSystemPrompt === "") return false;
      return sessionSystemPrompt !== modeDefaultPrompt;
    },
    get systemPromptDraft() {
      return systemPromptDraft;
    },
    get systemPromptState() {
      return systemPromptState;
    },
    get systemPromptError() {
      return systemPromptState.status === "error" ? systemPromptState.message : "";
    },

    /** True when any edit/delete/truncate operation is in flight. */
    get isMutating() {
      return editState.status === "loading";
    },

    // ── Message editing ─────────────────────────────────────────────

    startEditing(turnId: string, messages: Message[]) {
      const msg = messages.find((m) => m.turn_id === turnId);
      if (!msg) return;
      editingTurnId = turnId;
      editDraft = msg.content;
      editState = { status: "idle" };
    },

    cancelEditing() {
      editingTurnId = null;
      editDraft = "";
      editState = { status: "idle" };
    },

    setEditDraft(text: string) {
      editDraft = text;
    },

    async saveEdit(
      sessionId: string,
      messages: Message[],
      onUpdate: (idx: number, updated: Message) => void,
    ): Promise<void> {
      if (!editingTurnId || !editDraft.trim()) return;
      const turnId = editingTurnId;
      editState = { status: "loading" };
      try {
        await api.editMessage(sessionId, turnId, editDraft);
        // Optimistic local update — find by turn_id, not by index.
        const idx = messages.findIndex((m) => m.turn_id === turnId);
        if (idx !== -1) {
          onUpdate(idx, { ...messages[idx], content: editDraft });
        }
        editingTurnId = null;
        editDraft = "";
        editState = { status: "success", data: undefined };
      } catch (e) {
        editState = {
          status: "error",
          message: e instanceof Error ? e.message : "Edit failed.",
        };
      }
    },

    async deleteMessage(
      sessionId: string,
      messages: Message[],
      turnId: string,
      deletePair: boolean,
      onReplace: (newMessages: Message[]) => void,
    ): Promise<void> {
      if (editState.status === "loading") return;

      // Auto-cancel edit if deleting the message currently being edited.
      if (editingTurnId === turnId) {
        this.cancelEditing();
      }

      // Auto-promote to pair-delete.
      const idx = messages.findIndex((m) => m.turn_id === turnId);
      if (idx !== -1 && messages[idx].role === "user" && !deletePair) {
        const next = messages[idx + 1];
        if (next?.role === "assistant") {
          deletePair = true;
        }
      }

      // Snapshot for rollback.
      const snapshot = [...messages];

      // Optimistic local removal.
      if (deletePair) {
        onReplace(
          messages.filter((m, i) => {
            if (m.turn_id === turnId) return false;
            if (i === idx + 1 && m.role === "assistant") return false;
            return true;
          }),
        );
      } else {
        onReplace(messages.filter((m) => m.turn_id !== turnId));
      }

      editState = { status: "loading" };
      try {
        await api.deleteMessage(sessionId, turnId, deletePair);
        editState = { status: "success", data: undefined };
      } catch (e) {
        onReplace(snapshot); // rollback
        editState = {
          status: "error",
          message: e instanceof Error ? e.message : "Delete failed.",
        };
      }
    },

    // ── System prompt ──────────────────────────────────────────────

    /**
     * Load the mode's default system prompt from the API.
     * Called on mount and when the mode changes.
     */
    async loadModeDefaultPrompt(modeId: string) {
      try {
        const detail = await api.getPromptModeDetail(modeId);
        modeDefaultPrompt = detail.content ?? "";
      } catch {
        modeDefaultPrompt = "";
      }
    },

    /**
     * Load the session's system prompt override from the backend.
     * Called on session load. null = no override (use mode default).
     */
    async loadSystemPrompt(sessionId: string) {
      systemPromptState = { status: "loading" };
      try {
        const data = await api.getSystemPrompt(sessionId);
        sessionSystemPrompt = data.system_prompt ?? null;
        systemPromptState = { status: "success", data: undefined };
      } catch (e) {
        systemPromptState = {
          status: "error",
          message: e instanceof Error ? e.message : "Failed to load system prompt.",
        };
      }
    },

    /** Save a new system prompt override for the session. */
    async saveSystemPrompt(sessionId: string, newPrompt: string) {
      systemPromptState = { status: "loading" };
      try {
        await api.updateSystemPrompt(sessionId, newPrompt);
        sessionSystemPrompt = newPrompt;
        systemPromptState = { status: "success", data: undefined };
      } catch (e) {
        systemPromptState = {
          status: "error",
          message: e instanceof Error ? e.message : "Failed to save system prompt.",
        };
      }
    },

    /** Clear the session override, reverting to mode default. */
    async clearSystemPrompt(sessionId: string) {
      systemPromptState = { status: "loading" };
      try {
        await api.updateSystemPrompt(sessionId, "");
        sessionSystemPrompt = null;
        systemPromptState = { status: "success", data: undefined };
      } catch (e) {
        systemPromptState = {
          status: "error",
          message: e instanceof Error ? e.message : "Failed to clear system prompt.",
        };
      }
    },

    /** Reset all editor state. Called on startNewChat / loadSession. */
    reset() {
      editingTurnId = null;
      editDraft = "";
      editState = { status: "idle" };
      sessionSystemPrompt = null;
      // modeDefaultPrompt persists — it's mode-scoped, not session-scoped
      systemPromptDraft = "";
      systemPromptState = { status: "idle" };
    },
  };
}

export const editorStore = createEditorStore();

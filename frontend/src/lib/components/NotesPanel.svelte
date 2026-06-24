<script lang="ts">
  /**
   * NotesPanel
   * ===========
   * Displays all notes for the active session.
   * Mounted as a third tab inside ContextSidebar.
   *
   * Loads notes on mount (cached — no double-fetch on tab switch).
   * Deletes are optimistic via notesStore.
   *
   * Props:
   *   sessionId — the currently active session.
   */
  import { SvelteSet } from "svelte/reactivity";
  import { untrack } from "svelte";
  import type { Note } from "$lib/api";
  import { notesStore } from "$lib/stores/notes.svelte";

  type Props = {
    sessionId: string;
    oninsertnotes: (notes: Note[]) => void;
  };

  let { sessionId, oninsertnotes }: Props = $props();

  // Load on mount and whenever sessionId changes.
  $effect(() => {
    const id = sessionId;
    untrack(() => {
      notesStore.load(id);
    });
  });

  const notes = $derived(notesStore.forSession(sessionId));
  const fetchState = $derived(notesStore.fetchStateFor(sessionId));
  let selectedNoteIds = new SvelteSet<string>();
  const selectedNotes = $derived(notes.filter((note) => selectedNoteIds.has(note.id)));
  let deleteError = $state("");
  let deleteErrorTimer: ReturnType<typeof setTimeout>;

  $effect(() => {
    untrack(() => {
      selectedNoteIds.clear();
    });
  });

  function toggleNote(noteId: string) {
    if (selectedNoteIds.has(noteId)) {
      selectedNoteIds.delete(noteId);
    } else {
      selectedNoteIds.add(noteId);
    }
  }

  function insertSelected() {
    if (selectedNotes.length === 0) return;
    oninsertnotes(selectedNotes);
    selectedNoteIds.clear();
  }

  async function remove(noteId: string) {
    clearTimeout(deleteErrorTimer);
    deleteError = "";
    selectedNoteIds.delete(noteId);
    try {
      await notesStore.delete(sessionId, noteId);
    } catch (e) {
      deleteError = `Delete failed: ${e}`;
      deleteErrorTimer = setTimeout(() => (deleteError = ""), 4000);
    }
  }

  function formatDate(iso: string): string {
    try {
      return new Date(iso).toLocaleDateString("pl-PL", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }
</script>

<div class="flex flex-col overflow-hidden p-3">
  <!-- Header -->
  <div class="mb-3 flex items-center justify-between">
    <p class="text-xs font-semibold tracking-wide text-muted uppercase">Notes</p>
    <div class="flex items-center gap-2">
      {#if selectedNotes.length > 0}
        <button
          onclick={insertSelected}
          class="rounded bg-accent px-2 py-1 text-xs font-semibold text-white transition hover:bg-accent-strong focus:ring-2 focus:ring-accent focus:outline-none"
        >
          Insert {selectedNotes.length}
        </button>
      {/if}
      {#if notes.length > 0}
        <span class="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">
          {notes.length}
        </span>
      {/if}
    </div>
  </div>

  <!-- Description -->
  <p class="mb-3 text-xs leading-4 text-muted">
    Select text in any chat bubble to annotate it. Notes are saved per session.
  </p>

  <!-- Delete error toast -->
  {#if deleteError}
    <div
      class="mb-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-red-700"
      role="alert"
    >
      {deleteError}
    </div>
  {/if}

  <!-- Loading skeleton -->
  {#if fetchState.status === "loading"}
    <div class="space-y-2">
      {#each [1, 2] as i (i)}
        <div class="h-16 animate-pulse rounded-md bg-line"></div>
      {/each}
    </div>

    <!-- Fetch error -->
  {:else if fetchState.status === "error"}
    <p class="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">
      {fetchState.message}
    </p>

    <!-- Empty state -->
  {:else if notes.length === 0}
    <div
      class="flex flex-col items-center gap-2 rounded-md border border-dashed border-line
			       bg-surface p-4 text-center"
    >
      <span class="text-xl" aria-hidden="true">📌</span>
      <p class="text-xs text-muted">No notes yet. Select text in a chat message to add one.</p>
    </div>

    <!-- Notes list -->
  {:else}
    <ul class="min-h-0 flex-1 space-y-2 overflow-y-auto">
      {#each notes as note (note.id)}
        <li
          class="group rounded-lg border bg-surface p-2.5 text-xs transition
						       {selectedNoteIds.has(note.id)
            ? 'border-accent shadow-[inset_3px_0_0_var(--color-accent)]'
            : 'border-line hover:border-accent-soft'}"
        >
          <!-- Role badge + date -->
          <div class="mb-1.5 flex items-center justify-between gap-2">
            <label class="flex min-w-0 items-center gap-1.5">
              <input
                type="checkbox"
                checked={selectedNoteIds.has(note.id)}
                onchange={() => toggleNote(note.id)}
                class="h-3.5 w-3.5 shrink-0 accent-accent"
                aria-label="Select note"
              />
              <span
                class="rounded-full border border-line px-1.5 py-0.5 text-[10px] font-medium
									       {note.source_role === 'assistant' ? 'text-accent' : 'text-muted'}"
              >
                {note.source_role}
              </span>
            </label>
            <span class="text-[10px] text-muted">{formatDate(note.created_at)}</span>
          </div>

          <!-- Selected text -->
          <blockquote
            class="mb-1.5 line-clamp-2 border-l-2 border-accent pl-2 text-xs leading-4
						       text-muted italic"
            title={note.selected_text}
          >
            {note.selected_text}
          </blockquote>

          <!-- Annotation (may be empty) -->
          {#if note.note}
            <p class="leading-4 text-ink">{note.note}</p>
          {/if}

          <!-- Delete button (shown on hover) -->
          <div class="mt-2 flex justify-end opacity-0 transition group-hover:opacity-100">
            <button
              onclick={() => remove(note.id)}
              class="rounded px-1.5 py-0.5 text-[10px] text-muted hover:bg-red-50
							       hover:text-red-600 focus:outline-none"
              aria-label="Delete note"
            >
              Remove
            </button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>

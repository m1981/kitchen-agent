<script lang="ts">
  /**
   * NotePopup
   * ==========
   * Floating popup that appears at the cursor position when the user
   * selects text inside a chat bubble and releases the mouse.
   *
   * The user can type an optional annotation, then hit "Save note".
   * On success the popup closes after a brief flash; on error it stays open.
   *
   * State machine: 'idle' | 'saving' | 'saved' | 'error'
   *
   * Props:
   *   selectedText  — the highlighted string.
   *   x / y         — cursor position for absolute placement.
   *   sessionId     — which session to attach the note to.
   *   sourceRole    — 'user' | 'assistant' (from which bubble).
   *   ondismiss     — called when the popup should close.
   */
  import { notesStore } from "$lib/stores/notes.svelte";
  import { focusTrap } from "$lib/actions/focustrap";

  type SaveState = "idle" | "saving" | "saved" | "error";

  type Props = {
    selectedText: string;
    x: number;
    y: number;
    sessionId: string;
    sourceRole: "user" | "assistant";
    ondismiss: () => void;
  };

  let { selectedText, x, y, sessionId, sourceRole, ondismiss }: Props = $props();

  let noteText = $state("");
  let saveState = $state<SaveState>("idle");
  let errorMsg = $state("");

  async function save() {
    saveState = "saving";
    errorMsg = "";
    try {
      await notesStore.create(sessionId, {
        selected_text: selectedText,
        source_role: sourceRole,
        note: noteText.trim(),
      });
      saveState = "saved";
      // Brief success flash, then dismiss.
      setTimeout(ondismiss, 900);
    } catch (e) {
      saveState = "error";
      errorMsg = String(e);
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") ondismiss();
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) save();
  }
</script>

<div
  role="dialog"
  aria-modal="true"
  aria-label="Add note"
  tabindex="-1"
  use:focusTrap
  onkeydown={handleKeydown}
  class="note-popup fixed z-50 w-72 rounded-xl border border-line bg-panel p-3 shadow-2xl"
  style="left: {x}px; top: {y}px;"
>
  <!-- Header -->
  <div class="mb-2 flex items-center justify-between">
    <p class="text-xs font-semibold text-ink">📌 Add note</p>
    <button
      onclick={ondismiss}
      class="rounded p-0.5 text-muted hover:text-ink focus:outline-none"
      aria-label="Close"
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
        <path
          d="M1 1l10 10M11 1L1 11"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </button>
  </div>

  <!-- Selected text preview -->
  <blockquote
    class="mb-2 line-clamp-2 rounded bg-surface px-2 py-1.5 text-xs leading-5 text-muted italic"
    title={selectedText}
  >
    "{selectedText}"
  </blockquote>

  <!-- Note textarea -->
  {#if saveState !== "saved"}
    <textarea
      bind:value={noteText}
      rows="2"
      placeholder="Optional annotation… (Ctrl+Enter to save)"
      class="w-full resize-none rounded border border-line bg-surface px-2 py-1.5 text-xs
			       leading-5 text-ink placeholder:text-muted focus:border-accent focus:outline-none"
    ></textarea>
  {/if}

  <!-- Error -->
  {#if saveState === "error"}
    <p class="mt-1 text-xs text-red-600">{errorMsg}</p>
  {/if}

  <!-- Actions / status -->
  <div class="mt-2 flex items-center gap-2">
    {#if saveState === "saved"}
      <p class="flex-1 text-center text-xs font-semibold text-accent">✓ Note saved</p>
    {:else}
      <button
        onclick={save}
        disabled={saveState === "saving"}
        class="flex-1 rounded-md bg-accent px-2 py-1.5 text-xs font-semibold text-white
				       transition hover:bg-accent-strong focus:ring-2 focus:ring-accent focus:ring-offset-1
				       focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
      >
        {saveState === "saving" ? "Saving…" : "Save note"}
      </button>
      <button
        onclick={ondismiss}
        class="rounded-md border border-line px-2 py-1.5 text-xs text-muted
				       transition hover:text-ink"
      >
        Cancel
      </button>
    {/if}
  </div>
</div>

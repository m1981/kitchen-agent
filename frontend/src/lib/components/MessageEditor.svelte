<script lang="ts">
  /**
   * MessageEditor
   * ==============
   * Inline editor that appears inside a chat bubble when the user clicks
   * the ✏️ Edit button.
   *
   * Features:
   *   - Textarea pre-filled with the message's current content.
   *   - Save (Enter / button) — persists via the API, closes on success.
   *   - Cancel (Escape / button) — discards edits.
   *   - Shows a spinner while saving and an error badge on failure.
   *
   * Props:
   *   draft        — bindable current draft text
   *   isSaving     — true while the API call is in flight
   *   errorMessage — non-empty string shown as an error badge
   *   onsave       — called when the user confirms the edit
   *   oncancel     — called when the user cancels
   */

  import { tick } from "svelte";

  type Props = {
    draft: string;
    isSaving: boolean;
    errorMessage: string;
    onsave: () => void;
    oncancel: () => void;
    ondraftchange: (text: string) => void;
  };

  let { draft, isSaving, errorMessage, onsave, oncancel, ondraftchange }: Props = $props();

  let textareaEl = $state<HTMLTextAreaElement | null>(null);

  // Auto-focus when the editor mounts.
  $effect(() => {
    tick().then(() => textareaEl?.focus());
  });

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onsave();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      oncancel();
    }
  }

  function handleInput(e: Event) {
    ondraftchange((e.target as HTMLTextAreaElement).value);
  }
</script>

<div class="mt-2 space-y-2" role="form" aria-label="Edit message">
  <textarea
    bind:this={textareaEl}
    value={draft}
    oninput={handleInput}
    onkeydown={handleKeydown}
    disabled={isSaving}
    rows={Math.max(2, draft.split("\n").length)}
    class="w-full resize-none rounded-md border border-accent bg-surface px-3 py-2 text-sm leading-6 text-ink focus:ring-2 focus:ring-accent focus:outline-none disabled:opacity-60"
    aria-label="Edit message content"
  ></textarea>

  {#if errorMessage}
    <p class="text-xs text-red-500" role="alert">{errorMessage}</p>
  {/if}

  <div class="flex items-center gap-2">
    <button
      onclick={onsave}
      disabled={isSaving || !draft.trim()}
      class="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-accent-strong focus:ring-2 focus:ring-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
    >
      {#if isSaving}
        Saving…
      {:else}
        Save <kbd class="ml-1 font-mono opacity-70">↵</kbd>
      {/if}
    </button>
    <button
      onclick={oncancel}
      disabled={isSaving}
      class="rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/60 hover:text-ink focus:ring-2 focus:ring-accent focus:outline-none disabled:opacity-50"
    >
      Cancel <kbd class="ml-1 font-mono opacity-70">Esc</kbd>
    </button>
  </div>
</div>

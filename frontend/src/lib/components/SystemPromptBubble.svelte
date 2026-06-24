<script lang="ts">
  /**
   * SystemPromptBubble
   * ===================
   * Compact, collapsible bubble for the active system prompt.
   * Collapsed by default — shows a single header line with a chevron.
   * Expand to view/edit the full prompt text.
   */

  import type { AsyncState } from "$lib/types";
  import { tick } from "svelte";

  type Props = {
    text: string;
    isOverride: boolean;
    modeLabel: string;
    saveState: AsyncState<void>;
    errorMessage: string;
    onsave: (newText: string) => void;
    onreset: () => void;
  };

  let { text, isOverride, modeLabel, saveState, errorMessage, onsave, onreset }: Props = $props();

  let isEditing = $state(false);
  let isExpanded = $state(false);
  let draft = $state("");
  let textareaEl = $state<HTMLTextAreaElement | null>(null);

  $effect(() => {
    if (text) {
      isEditing = false;
      draft = "";
    }
  });

  function startEditing() {
    draft = text;
    isEditing = true;
    isExpanded = true;
    tick().then(() => textareaEl?.focus());
  }

  function cancelEditing() {
    isEditing = false;
    draft = "";
  }

  function handleSave() {
    if (draft.trim()) {
      onsave(draft.trim());
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSave();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      cancelEditing();
    }
  }

  const isBusy = $derived(saveState.status === "loading");
</script>

<article
  data-testid="system-prompt"
  class="rounded-lg border bg-panel/60 shadow-sm {isOverride
    ? 'border-l-4 border-line border-l-accent'
    : 'border-l-4 border-line border-l-line'}"
  aria-label="System prompt"
>
  <!-- Header — clickable to expand/collapse -->
  <button
    type="button"
    class="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left transition hover:bg-surface/50"
    onclick={() => (isExpanded = !isExpanded)}
    aria-expanded={isExpanded}
  >
    <div class="flex min-w-0 items-center gap-2">
      <span class="text-xs font-semibold tracking-[0.14em] text-muted uppercase"> Prompt </span>
      {#if !isEditing && !isExpanded}
        <span class="truncate text-xs text-muted/60">
          {text
            ? text.split("\n")[0].slice(0, 50) + (text.split("\n")[0].length > 50 ? "…" : "")
            : "Not set"}
        </span>
      {/if}
      {#if isOverride}
        <span
          class="rounded-full border border-accent-soft bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent"
        >
          custom
        </span>
      {/if}
      <span
        class="rounded-full border border-line bg-surface px-2 py-0.5 text-[10px] font-medium text-muted"
      >
        {modeLabel}
      </span>
    </div>

    <div class="flex shrink-0 items-center gap-1">
      {#if !isEditing}
        <span
          onclick={(e) => {
            e.stopPropagation();
            startEditing();
          }}
          role="button"
          tabindex="0"
          onkeydown={(e) => e.key === "Enter" && startEditing()}
          class="action-btn action-btn-assistant"
          title="Edit system prompt"
          aria-label="Edit system prompt"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </span>
        {#if isOverride}
          <span
            onclick={(e) => {
              e.stopPropagation();
              onreset();
            }}
            onkeydown={(e) => e.key === "Enter" && onreset()}
            role="button"
            tabindex="0"
            class="action-btn action-btn-assistant"
            title="Reset to mode default"
            aria-label="Reset to mode default"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
          </span>
        {/if}
      {/if}

      <!-- Chevron -->
      <svg
        class="h-4 w-4 text-muted transition-transform duration-200 {isExpanded
          ? 'rotate-180'
          : ''}"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
  </button>

  <!-- Body — only visible when expanded or editing -->
  {#if isExpanded || isEditing}
    <div class="border-t border-line px-4 py-3">
      {#if isEditing}
        <div class="space-y-2">
          <textarea
            bind:this={textareaEl}
            bind:value={draft}
            onkeydown={handleKeydown}
            disabled={isBusy}
            rows={Math.max(4, draft.split("\n").length)}
            class="w-full resize-y rounded-md border border-accent bg-surface px-3 py-2 font-mono text-xs leading-5 text-ink focus:ring-2 focus:ring-accent focus:outline-none disabled:opacity-60"
            placeholder="Enter a custom system prompt for this session…"
            spellcheck="false"
          ></textarea>

          {#if errorMessage}
            <p class="text-xs text-red-500" role="alert">{errorMessage}</p>
          {/if}

          <div class="flex items-center gap-2">
            <button
              onclick={handleSave}
              disabled={isBusy || !draft.trim()}
              class="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-accent-strong focus:ring-2 focus:ring-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              {#if isBusy}
                Saving…
              {:else}
                Save <kbd class="ml-1 font-mono opacity-70">⌘↵</kbd>
              {/if}
            </button>
            <button
              onclick={cancelEditing}
              disabled={isBusy}
              class="rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/60 hover:text-ink focus:ring-2 focus:ring-accent focus:outline-none disabled:opacity-50"
            >
              Cancel <kbd class="ml-1 font-mono opacity-70">Esc</kbd>
            </button>
          </div>
        </div>
      {:else if text}
        <pre
          class="max-h-60 overflow-auto font-mono text-xs leading-5 break-words whitespace-pre-wrap text-ink">{text}</pre>
      {:else}
        <p class="text-xs text-muted italic">No system prompt set for this session.</p>
      {/if}
    </div>
  {/if}
</article>

<style>
  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 4px;
    transition: all 0.15s ease;
    cursor: pointer;
  }

  .action-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .action-btn-assistant {
    color: var(--color-muted, #6b7280);
  }

  .action-btn-assistant:hover:not(:disabled) {
    background: var(--color-line, #e5e7eb);
    color: var(--color-ink, #111827);
  }
</style>

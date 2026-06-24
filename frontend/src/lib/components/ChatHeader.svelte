<script lang="ts">
  /**
   * ChatHeader
   * ===========
   * Compact header with sidebar toggle and session title.
   * Badges moved to system prompt bubble.
   */

  type Props = {
    sessionId: string;
    title?: string | null;
    showLeft: boolean;
    ontoggleleft: () => void;
    onsave?: (newTitle: string) => void;
  };

  let { sessionId, title = null, showLeft, ontoggleleft, onsave }: Props = $props();

  const displayTitle = $derived(title ?? `Session ${sessionId.substring(0, 8)}`);

  let isEditing = $state(false);
  let draft = $state("");
  let inputEl = $state<HTMLInputElement | null>(null);

  function startEditing() {
    draft = displayTitle;
    isEditing = true;
    requestAnimationFrame(() => {
      inputEl?.focus();
      inputEl?.select();
    });
  }

  function cancelEditing() {
    isEditing = false;
    draft = "";
  }

  function saveEditing() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== displayTitle) {
      onsave?.(trimmed);
    }
    isEditing = false;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      saveEditing();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelEditing();
    }
  }
</script>

<header
  class="sticky top-0 z-40 flex h-12 items-center border-b border-line/50 bg-panel/80 px-3 backdrop-blur-md md:px-4"
>
  <div class="flex w-full items-center gap-2">
    <!-- Sidebar toggle (hamburger icon) -->
    <button
      onclick={ontoggleleft}
      data-testid="sidebar-toggle"
      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted transition hover:bg-surface/80 hover:text-ink"
      title={showLeft ? "Hide sidebar" : "Show sidebar"}
      aria-label={showLeft ? "Hide sidebar" : "Show sidebar"}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      >
        {#if showLeft}
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        {:else}
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        {/if}
      </svg>
    </button>

    <!-- Title (single line, truncated) -->
    {#if isEditing}
      <input
        bind:this={inputEl}
        bind:value={draft}
        onkeydown={handleKeydown}
        onblur={saveEditing}
        class="h-8 min-w-0 flex-1 rounded-md border border-accent bg-surface px-2 text-base font-medium text-ink shadow-sm outline-none focus:ring-2 focus:ring-accent/50"
        maxlength="100"
      />
    {:else}
      <button
        type="button"
        class="min-w-0 flex-1 truncate text-left text-base font-medium text-ink transition hover:bg-surface/80"
        onclick={startEditing}
        title="Click to edit title"
      >
        {displayTitle}
      </button>
    {/if}
  </div>
</header>

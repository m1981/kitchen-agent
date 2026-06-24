<script lang="ts">
  /**
   * SessionContextMenu
   * ==================
   * A ⋯ button that opens a small popover with per-session actions:
   *   Export Markdown / Export LLM JSON / Archive / Restore / Delete
   *   + optional: Regenerate Title / Remove from folder
   *
   * State machine:
   *   'closed' | 'open' | 'confirming-delete' | 'exporting-md' | 'exporting-llm'
   *
   * No boolean flags — impossible states are unrepresentable.
   * Both export states share the same spinner UI; label differs by type.
   */
  import { focusTrap } from "$lib/actions/focustrap";
  import { smartPosition } from "$lib/actions/smartPosition";
  import type { SessionNode } from "$lib/api";

  type MenuState =
    | "closed"
    | "open"
    | "confirming-delete"
    | "exporting-md"
    | "exporting-llm"
    | "generating-title";

  type Props = {
    node: SessionNode;
    onarchive: (id: string) => void;
    onunarchive: (id: string) => void;
    ondelete: (id: string) => void;
    onexport: (id: string) => Promise<void>;
    onexportllm: (id: string) => Promise<void>;
    /** Called when user clicks "Regenerate Title". */
    ontitlegenerate?: (id: string) => Promise<void>;
    /** Called when user clicks "Remove from folder". Only shown when provided. */
    onremovefromfolder?: (id: string) => void;
  };

  let {
    node,
    onarchive,
    onunarchive,
    ondelete,
    onexport,
    onexportllm,
    ontitlegenerate,
    onremovefromfolder,
  }: Props = $props();

  let menuState = $state<MenuState>("closed");
  let errorMsg = $state("");
  let triggerEl = $state<HTMLButtonElement | null>(null);

  const isArchived = $derived(node.archived_at !== null);
  const isBusy = $derived(
    menuState === "exporting-md" ||
      menuState === "exporting-llm" ||
      menuState === "generating-title",
  );

  function open(e: MouseEvent) {
    e.stopPropagation();
    menuState = menuState === "open" ? "closed" : "open";
    errorMsg = "";
  }

  function close() {
    menuState = "closed";
    errorMsg = "";
  }

  function handleArchive(e: MouseEvent) {
    e.stopPropagation();
    close();
    if (isArchived) {
      onunarchive(node.id);
    } else {
      onarchive(node.id);
    }
  }

  function startDelete(e: MouseEvent) {
    e.stopPropagation();
    menuState = "confirming-delete";
  }

  function confirmDelete(e: MouseEvent) {
    e.stopPropagation();
    close();
    ondelete(node.id);
  }

  function cancelDelete(e: MouseEvent) {
    e.stopPropagation();
    menuState = "open";
  }

  async function handleExport(e: MouseEvent) {
    e.stopPropagation();
    menuState = "exporting-md";
    errorMsg = "";
    try {
      await onexport(node.id);
      menuState = "closed";
    } catch (err) {
      errorMsg = `Export failed: ${err instanceof Error ? err.message : String(err)}`;
      menuState = "open";
    }
  }

  async function handleExportLlm(e: MouseEvent) {
    e.stopPropagation();
    menuState = "exporting-llm";
    errorMsg = "";
    try {
      await onexportllm(node.id);
      menuState = "closed";
    } catch (err) {
      errorMsg = `LLM export failed: ${err instanceof Error ? err.message : String(err)}`;
      menuState = "open";
    }
  }

  async function handleTitleGenerate(e: MouseEvent) {
    e.stopPropagation();
    if (!ontitlegenerate) return;
    menuState = "generating-title";
    errorMsg = "";
    try {
      await ontitlegenerate(node.id);
      menuState = "closed";
    } catch (err) {
      errorMsg = `Title generation failed: ${err instanceof Error ? err.message : String(err)}`;
      menuState = "open";
    }
  }
</script>

<!-- Click-outside backdrop (invisible, closes menu) -->
{#if menuState !== "closed"}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fixed inset-0 z-30" onclick={close}></div>
{/if}

<div class="relative">
  <!-- ⋯ trigger button — shows spinner while either export is in flight -->
  <button
    onclick={open}
    bind:this={triggerEl}
    title="Session options"
    aria-label="Session options"
    aria-expanded={menuState !== "closed"}
    disabled={isBusy}
    class="flex h-5 w-5 items-center justify-center rounded text-muted transition
		       group-hover:opacity-100 hover:bg-line hover:text-ink focus:opacity-100 focus:outline-none
		       {menuState !== 'closed' ? 'opacity-100' : 'opacity-45'}
		       disabled:cursor-wait disabled:opacity-60"
  >
    {#if isBusy}
      <svg
        class="animate-spin"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" stroke-opacity="0.25" />
        <path d="M12 3 A9 9 0 0 1 21 12" />
      </svg>
    {:else}
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <circle cx="8" cy="3" r="1.4" />
        <circle cx="8" cy="8" r="1.4" />
        <circle cx="8" cy="13" r="1.4" />
      </svg>
    {/if}
  </button>

  {#if menuState === "open"}
    <div
      use:focusTrap
      use:smartPosition={{ trigger: triggerEl!, placement: "bottom-end" }}
      class="fixed z-40 min-w-[178px] rounded-lg border border-line bg-panel
			       py-1 shadow-lg"
    >
      <!-- Export Markdown -->
      <button
        onclick={handleExport}
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-ink
				       hover:bg-surface"
      >
        <span aria-hidden="true">⬇</span> Export Markdown
      </button>

      <!-- Export LLM JSON -->
      <button
        onclick={handleExportLlm}
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-ink
				       hover:bg-surface"
      >
        <span aria-hidden="true">⬇</span> Export LLM JSON
      </button>

      <div class="my-1 border-t border-line"></div>

      <!-- Archive / Restore -->
      <button
        onclick={handleArchive}
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-ink
				       hover:bg-surface"
      >
        {#if isArchived}
          <span aria-hidden="true">↩</span> Restore
        {:else}
          <span aria-hidden="true">📁</span> Archive
        {/if}
      </button>

      {#if ontitlegenerate}
        <div class="my-1 border-t border-line"></div>

        <!-- Regenerate Title -->
        <button
          onclick={handleTitleGenerate}
          class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-ink
					       hover:bg-surface"
        >
          <span aria-hidden="true">✨</span> Regenerate Title
        </button>
      {/if}

      {#if onremovefromfolder}
        <div class="my-1 border-t border-line"></div>

        <!-- Remove from folder -->
        <button
          onclick={(e) => {
            e.stopPropagation();
            close();
            onremovefromfolder(node.id);
          }}
          class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted
					       hover:bg-surface hover:text-ink"
        >
          <span aria-hidden="true">↩</span> Remove from folder
        </button>
      {/if}

      <div class="my-1 border-t border-line"></div>

      <!-- Delete -->
      <button
        onclick={startDelete}
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-red-600
				       hover:bg-red-50"
      >
        <span aria-hidden="true">🗑</span> Delete…
      </button>

      <!-- Inline error -->
      {#if errorMsg}
        <div class="border-t border-line px-3 py-2">
          <p class="text-xs text-red-600">{errorMsg}</p>
        </div>
      {/if}
    </div>
  {/if}

  {#if menuState === "confirming-delete"}
    <div
      use:focusTrap
      use:smartPosition={{ trigger: triggerEl!, placement: "bottom-end" }}
      class="fixed z-40 w-52 rounded-lg border border-red-200 bg-panel
			       p-3 shadow-lg"
    >
      <p class="mb-2 text-xs font-semibold text-ink">Delete this session?</p>
      <p class="mb-3 text-xs leading-4 text-muted">
        This is permanent. Children must be deleted first.
      </p>
      {#if errorMsg}
        <p class="mb-2 text-xs text-red-600">{errorMsg}</p>
      {/if}
      <div class="flex gap-2">
        <button
          onclick={confirmDelete}
          class="flex-1 rounded bg-red-600 px-2 py-1 text-xs font-semibold text-white
					       hover:bg-red-700"
        >
          Delete
        </button>
        <button
          onclick={cancelDelete}
          class="flex-1 rounded border border-line px-2 py-1 text-xs text-muted
					       hover:text-ink"
        >
          Cancel
        </button>
      </div>
    </div>
  {/if}
</div>

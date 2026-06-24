<script lang="ts">
  /**
   * ArchivedPanel
   * =============
   * Renders the archived sessions section with expand/collapse toggle.
   *
   * Props:
   *   activeId — currently loaded session ID (for highlight).
   *   onload   — called when user clicks a session title.
   */
  import { api } from "$lib/api";
  import { sessionStore } from "$lib/stores/sessions.svelte";
  import SessionTreeNode from "./SessionTreeNode.svelte";
  import DraggableSession from "./DraggableSession.svelte";

  type Props = {
    activeId: string | null;
    onload: (id: string) => void;
  };

  let { activeId, onload }: Props = $props();

  let archivedExpanded = $state(false);

  // ── Error toast for failed operations ────────────────────────────────────
  let opError = $state("");
  let opErrorTimer: ReturnType<typeof setTimeout>;

  function showError(msg: string) {
    clearTimeout(opErrorTimer);
    opError = msg;
    opErrorTimer = setTimeout(() => (opError = ""), 4000);
  }

  // ── Shared filename helper ────────────────────────────────────────────────
  function safeFilename(id: string): string {
    const node = sessionStore.flat.find((n) => n.id === id);
    const rawTitle = node?.title ?? id.slice(0, 8);
    return rawTitle
      .replace(/[/\\:*?"<>|]/g, "")
      .replace(/\s+/g, "-")
      .slice(0, 64)
      .toLowerCase();
  }

  function triggerDownload(content: string, filename: string, mimeType: string): void {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── Event handlers ───────────────────────────────────────────────────────
  async function handleArchive(id: string) {
    try {
      await sessionStore.archive(id);
    } catch (e) {
      showError(`Archive failed: ${e}`);
    }
  }

  async function handleUnarchive(id: string) {
    try {
      await sessionStore.unarchive(id);
    } catch (e) {
      showError(`Restore failed: ${e}`);
    }
  }

  async function handleDelete(id: string) {
    try {
      await sessionStore.delete(id);
    } catch (e) {
      const msg = String(e).includes("child")
        ? "Delete children first before deleting this session."
        : `Delete failed: ${e}`;
      showError(msg);
    }
  }

  async function handleExport(id: string): Promise<void> {
    const markdown = await api.exportSession(id);
    triggerDownload(markdown, `${safeFilename(id)}.md`, "text/markdown;charset=utf-8");
  }

  async function handleExportLlm(id: string): Promise<void> {
    const data = await api.exportSessionLlm(id);
    const json = JSON.stringify(data, null, 2);
    triggerDownload(json, `${safeFilename(id)}.llm.json`, "application/json;charset=utf-8");
  }

  // ── Derived state ────────────────────────────────────────────────────────
  const archivedRoots = $derived(sessionStore.tree.filter((n) => n.archived_at !== null));
  const archivedCount = $derived(sessionStore.flat.filter((n) => n.archived_at !== null).length);
  const activeArchived = $derived(
    activeId !== null && sessionStore.flat.some((n) => n.id === activeId && n.archived_at !== null),
  );

  $effect(() => {
    if (activeArchived) archivedExpanded = true;
  });
</script>

{#if archivedRoots.length > 0}
  <div class="mt-3 border-t border-line pt-2">
    <!-- Error toast -->
    {#if opError}
      <div
        class="mb-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-red-700"
        role="alert"
      >
        {opError}
      </div>
    {/if}

    <button
      type="button"
      onclick={() => (archivedExpanded = !archivedExpanded)}
      class="group flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-xs font-semibold tracking-[0.14em] text-muted uppercase transition hover:bg-surface hover:text-ink focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:outline-none"
      aria-expanded={archivedExpanded}
    >
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="currentColor"
        class="shrink-0 transition-transform {archivedExpanded ? 'rotate-90' : ''}"
        aria-hidden="true"
      >
        <path d="M3 2 L7 5 L3 8 Z" />
      </svg>
      <span class="min-w-0 flex-1 truncate">Archived</span>
      <span
        class="rounded-full border border-line bg-surface px-1.5 py-0.5 text-[10px] font-medium tracking-normal text-muted"
      >
        {archivedCount}
      </span>
    </button>

    {#if archivedExpanded}
      <div class="mt-1 flex flex-col gap-0.5">
        {#each archivedRoots as root (root.id)}
          <DraggableSession sessionId={root.id} sessionTitle={root.title ?? root.id.slice(0, 8)}>
            <SessionTreeNode
              node={root}
              depth={0}
              {activeId}
              {onload}
              onarchive={handleArchive}
              onunarchive={handleUnarchive}
              ondelete={handleDelete}
              onexport={handleExport}
              onexportllm={handleExportLlm}
            />
          </DraggableSession>
        {/each}
      </div>
    {/if}
  </div>
{/if}

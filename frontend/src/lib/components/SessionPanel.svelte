<script lang="ts">
  /**
   * SessionPanel
   * ============
   * Renders the "History" header, error toast, and session forest.
   *
   * Props:
   *   activeId — currently loaded session ID (for highlight).
   *   onload   — called when user clicks a session title.
   *   isStreaming — disables interactions during streaming.
   */
  import { api } from "$lib/api";
  import { sessionStore } from "$lib/stores/sessions.svelte";
  import { folderStore } from "$lib/stores/folder.svelte";
  import SessionTreeNode from "./SessionTreeNode.svelte";
  import DraggableSession from "./DraggableSession.svelte";

  type Props = {
    activeId: string | null;
    onload: (id: string) => void;
    isStreaming?: boolean;
  };

  let { activeId, onload, isStreaming = false }: Props = $props();

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

  async function handleTitleGenerate(id: string): Promise<void> {
    try {
      await api.generateSessionTitle(id);
      await sessionStore.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      showError(`Title generation failed: ${msg}`);
      throw e;
    }
  }

  // ── Derived state ────────────────────────────────────────────────────────
  // History shows only unfiled sessions (inbox model)
  const activeCount = $derived(
    sessionStore.flat.filter((n) => n.archived_at === null && !folderStore.isFoldered(n.id)).length,
  );
  const visibleRoots = $derived(
    sessionStore.tree.filter((n) => n.archived_at === null && !folderStore.isFoldered(n.id)),
  );
</script>

<!-- Header row -->
<section data-testid="history-panel">
  <div class="mb-2 flex items-center justify-between">
    <h2 class="text-xs font-semibold tracking-[0.16em] text-muted uppercase">History</h2>
    <div class="flex items-center gap-1.5">
      <span class="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">
        {activeCount}
      </span>
    </div>
  </div>

  <!-- Error toast -->
  {#if opError}
    <div
      class="mb-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-red-700"
      role="alert"
    >
      {opError}
    </div>
  {/if}

  <!-- Loading state -->
  {#if sessionStore.fetchState.status === "loading"}
    <div class="space-y-1.5">
      {#each [1, 2, 3] as i (i)}
        <div class="h-8 animate-pulse rounded-md bg-line"></div>
      {/each}
    </div>

    <!-- Error state -->
  {:else if sessionStore.fetchState.status === "error"}
    <p class="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">
      {sessionStore.fetchState.message}
    </p>

    <!-- Empty state -->
  {:else if visibleRoots.length === 0}
    <p class="rounded-md border border-dashed border-line bg-surface p-3 text-sm text-muted">
      No saved conversations yet.
    </p>

    <!-- Session forest -->
  {:else}
    <div class="flex flex-col gap-1 {isStreaming ? 'pointer-events-none opacity-50' : ''}">
      {#each visibleRoots as root (root.id)}
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
            ontitlegenerate={handleTitleGenerate}
          />
        </DraggableSession>
      {/each}
    </div>
  {/if}
</section>

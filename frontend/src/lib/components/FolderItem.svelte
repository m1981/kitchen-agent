<script lang="ts">
  import { api } from "$lib/api";
  import type { SessionNode } from "$lib/api";
  import { folderStore } from "$lib/stores/folder.svelte";
  import { sessionStore } from "$lib/stores/sessions.svelte";
  import { smartPosition } from "$lib/actions/smartPosition";
  import { draggable } from "$lib/actions/dragdrop";
  import SessionContextMenu from "./SessionContextMenu.svelte";
  import DraggableSession from "./DraggableSession.svelte";

  type Props = {
    folderId: string;
    activeId?: string | null;
    onloadsession?: (sessionId: string) => void;
  };

  let { folderId, activeId = null, onloadsession }: Props = $props();

  // Get folder from store reactively
  const folder = $derived(folderStore.getFolderById(folderId)!);
  const isExpanded = $derived(folderStore.isExpanded(folderId));
  const sessions = $derived(folderStore.getSessions(folderId));
  const isLoading = $derived(folderStore.sessionsLoading.get(folderId) ?? false);
  const sessionsError = $derived(folderStore.sessionsError.get(folderId) ?? null);

  let showMenu = $state(false);
  let menuRef = $state<HTMLElement | null>(null);
  let menuTriggerEl = $state<HTMLButtonElement | null>(null);

  // ── Inline rename state ───────────────────────────────────────────────
  const isEditing = $derived(folderStore.editingFolderId === folderId);
  let draft = $state("");
  let renameInputEl = $state<HTMLInputElement | null>(null);

  // Focus input when editing starts
  $effect(() => {
    if (isEditing) {
      draft = folder.name;
      requestAnimationFrame(() => {
        renameInputEl?.focus();
        renameInputEl?.select();
      });
    }
  });

  function saveRename() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== folder.name) {
      folderStore.updateFolder(folder.id, { name: trimmed });
    }
    folderStore.stopEditing();
  }

  function cancelRename() {
    folderStore.stopEditing();
    draft = "";
  }

  function handleRenameKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      saveRename();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelRename();
    }
  }

  // Close menu on outside click
  function handleClickOutside(e: MouseEvent) {
    if (menuRef && !menuRef.contains(e.target as Node)) {
      showMenu = false;
    }
  }

  $effect(() => {
    if (showMenu) {
      document.addEventListener("click", handleClickOutside);
      return () => document.removeEventListener("click", handleClickOutside);
    }
  });

  // ── Session node lookup ───────────────────────────────────────────────
  /**
   * Look up the full SessionNode from the session store for a folder session.
   * SessionContextMenu needs the full node (with archived_at, children, etc.).
   * Falls back to a minimal stub if the session tree hasn't loaded yet.
   */
  function getNodeForSession(sessionId: string): SessionNode {
    const node = sessionStore.flat.find((n) => n.id === sessionId);
    if (node) return node;
    // Fallback: construct a minimal SessionNode-compatible object
    const session = sessions.find((s) => s.id === sessionId);
    return {
      id: sessionId,
      title: session?.title ?? null,
      updated_at: session?.updated_at ?? null,
      parent_id: null,
      fork_turn_index: null,
      root_id: null,
      archived_at: null,
      children: [],
    };
  }

  // ── Error toast ────────────────────────────────────────────────────────
  let opError = $state("");
  let opErrorTimer: ReturnType<typeof setTimeout>;

  function showError(msg: string) {
    clearTimeout(opErrorTimer);
    opError = msg;
    opErrorTimer = setTimeout(() => (opError = ""), 4000);
  }

  // ── Shared filename helper ─────────────────────────────────────────────
  function safeFilename(id: string): string {
    const node = sessionStore.flat.find((n) => n.id === id);
    const rawTitle = node?.title ?? id.slice(0, 8);
    return rawTitle
      .replace(/[\\/:*?"<>|]/g, "")
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

  // ── Session actions (same as SessionPanel / ArchivedPanel) ─────────────
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

  async function handleDeleteSession(id: string) {
    try {
      await sessionStore.delete(id);
      // Also unassign from this folder (optimistic — session is gone anyway)
      await folderStore.unassignSession(folderId, id);
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
      // Also refresh folder sessions cache so the updated title shows
      folderStore.invalidateSessions(folderId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      showError(`Title generation failed: ${msg}`);
      throw e;
    }
  }

  // ── Folder menu actions ────────────────────────────────────────────────
  function handleRename() {
    showMenu = false;
    folderStore.startEditing(folder.id);
  }

  async function handleDeleteFolder() {
    showMenu = false;
    if (confirm(`Delete folder "${folder.name}"? Sessions will be unassigned but not deleted.`)) {
      await folderStore.deleteFolder(folder.id);
    }
  }

  function handleColorChange(color: string) {
    showMenu = false;
    folderStore.updateFolder(folder.id, { color });
  }

  // Color palette
  const colors = [
    { name: "Gray", hex: "#6B7280" },
    { name: "Red", hex: "#EF4444" },
    { name: "Orange", hex: "#F97316" },
    { name: "Yellow", hex: "#EAB308" },
    { name: "Green", hex: "#22C55E" },
    { name: "Blue", hex: "#3B82F6" },
    { name: "Purple", hex: "#A855F7" },
    { name: "Pink", hex: "#EC4899" },
  ];
</script>

<div class="rounded-md transition hover:bg-surface">
  <!-- Error toast -->
  {#if opError}
    <div
      class="mx-1.5 mb-1 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-red-700"
      role="alert"
    >
      {opError}
    </div>
  {/if}

  <!-- Folder header row -->
  <div
    use:draggable={{
      payload: { type: "folder", id: folderId, title: folder.name },
      ondragstart: (p) => folderStore.startDrag(p),
      ondragend: () => folderStore.endDrag(),
    }}
    class="group flex items-center gap-1 px-1.5 py-1"
  >
    <!-- Drag handle -->
    <span
      class="flex h-4 w-3 shrink-0 cursor-grab items-center justify-center text-[10px] leading-none text-muted opacity-0 transition group-hover:opacity-60 hover:!opacity-100"
      aria-label="Drag to reorder {folder.name}"
      title="Drag to reorder"
    >
      ⋮⋮
    </span>

    <!-- Expand/collapse toggle -->
    <button
      type="button"
      onclick={() => folderStore.toggleExpand(folderId)}
      class="flex h-4 w-4 shrink-0 items-center justify-center text-muted transition-transform"
      aria-expanded={isExpanded}
      aria-label="{isExpanded ? 'Collapse' : 'Expand'} {folder.name}"
    >
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="currentColor"
        class="transition-transform {isExpanded ? 'rotate-90' : ''}"
      >
        <path d="M3 2 L7 5 L3 8 Z" />
      </svg>
    </button>

    <!-- Color dot -->
    <span
      class="h-3 w-3 shrink-0 rounded-full"
      style="background-color: {folder.color}"
      aria-hidden="true"
    ></span>

    <!-- Folder name (editable) -->
    {#if isEditing}
      <input
        bind:this={renameInputEl}
        bind:value={draft}
        onkeydown={handleRenameKeydown}
        onblur={saveRename}
        onclick={(e) => e.stopPropagation()}
        class="h-6 min-w-0 flex-1 rounded border border-accent bg-surface px-1.5 text-sm text-ink outline-none focus:ring-1 focus:ring-accent/50"
        maxlength="50"
      />
    {:else}
      <button
        type="button"
        onclick={() => folderStore.toggleExpand(folderId)}
        class="min-w-0 flex-1 truncate text-left text-sm text-ink"
      >
        {folder.icon}
        {folder.name}
      </button>
    {/if}

    <!-- Session count badge -->
    {#if folder.session_count > 0}
      <span
        class="rounded-full border border-line bg-surface px-1.5 py-0.5 text-[10px] font-medium text-muted"
      >
        {folder.session_count}
      </span>
    {/if}

    <!-- Folder context menu button -->
    <button
      type="button"
      bind:this={menuTriggerEl}
      onclick={(e) => {
        e.stopPropagation();
        showMenu = !showMenu;
      }}
      class="flex h-5 w-5 items-center justify-center rounded text-muted opacity-45 transition group-hover:opacity-100 hover:bg-line hover:text-ink focus:opacity-100 focus:outline-none"
      aria-label="Folder options"
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
        <circle cx="7" cy="3" r="1.5" />
        <circle cx="7" cy="7" r="1.5" />
        <circle cx="7" cy="11" r="1.5" />
      </svg>
    </button>
  </div>

  <!-- Expanded: show sessions (derived from store — no $effect needed) -->
  {#if isExpanded}
    <div class="ml-1 border-l border-line pb-0.5 pl-1">
      {#if isLoading}
        <div class="space-y-1 py-1">
          {#each [1, 2] as i (i)}
            <div class="h-6 animate-pulse rounded bg-line"></div>
          {/each}
        </div>
      {:else if sessionsError}
        <p class="py-1 text-xs text-red-600">{sessionsError}</p>
      {:else if sessions.length === 0}
        <p class="py-1 text-xs text-muted italic">No sessions in this folder</p>
      {:else}
        <div class="flex flex-col gap-0.5">
          {#each sessions as session (session.id)}
            {@const isPending = folderStore.pendingOps.has(session.id)}
            {@const isActive = session.id === activeId}
            {@const node = getNodeForSession(session.id)}
            <DraggableSession
              sessionId={session.id}
              sessionTitle={session.title ?? session.id.slice(0, 8)}
              sourceFolderId={folderId}
            >
              <div
                class="group flex w-full items-center gap-1 rounded-md px-1.5 py-1
									transition
									{isActive ? 'bg-accent-soft shadow-[inset_3px_0_0_var(--color-accent)]' : 'hover:bg-surface'}
									{isPending ? 'animate-pulse opacity-50' : ''}"
              >
                <!-- Session title (clickable) -->
                <button
                  type="button"
                  onclick={() => onloadsession?.(session.id)}
                  disabled={isPending}
                  class="min-w-0 flex-1 truncate text-left text-sm
										{isActive ? 'font-semibold text-ink' : 'font-medium text-muted group-hover:text-ink'}"
                  title={session.title}
                >
                  {session.title}
                </button>

                <!-- Full context menu with all session actions -->
                <SessionContextMenu
                  {node}
                  onarchive={handleArchive}
                  onunarchive={handleUnarchive}
                  ondelete={handleDeleteSession}
                  onexport={handleExport}
                  onexportllm={handleExportLlm}
                  ontitlegenerate={handleTitleGenerate}
                  onremovefromfolder={(id) => folderStore.unassignSession(folderId, id)}
                />
              </div>
            </DraggableSession>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- Folder context menu dropdown -->
{#if showMenu}
  <div
    bind:this={menuRef}
    use:smartPosition={{ trigger: menuTriggerEl!, placement: "bottom-end" }}
    class="fixed z-50 min-w-[160px] rounded-md border border-line bg-surface py-1 shadow-lg"
    role="menu"
  >
    <button
      type="button"
      onclick={handleRename}
      class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-ink hover:bg-surface"
      role="menuitem"
    >
      ✏️ Rename
    </button>

    <!-- Color submenu -->
    <div class="border-t border-line px-3 py-1.5">
      <p class="mb-1 text-[10px] font-semibold text-muted uppercase">Color</p>
      <div class="flex gap-1">
        {#each colors as color (color.hex)}
          <button
            type="button"
            onclick={() => handleColorChange(color.hex)}
            class="h-5 w-5 rounded-full transition-transform hover:scale-110 {folder.color ===
            color.hex
              ? 'ring-2 ring-accent ring-offset-1'
              : ''}"
            style="background-color: {color.hex}"
            aria-label={color.name}
            title={color.name}
          ></button>
        {/each}
      </div>
    </div>

    <div class="border-t border-line">
      <button
        type="button"
        onclick={handleDeleteFolder}
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
        role="menuitem"
      >
        🗑️ Delete
      </button>
    </div>
  </div>
{/if}

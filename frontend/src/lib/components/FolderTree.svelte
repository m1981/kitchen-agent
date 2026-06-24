<script lang="ts">
  import { folderStore } from "$lib/stores/folder.svelte";
  import { droppable } from "$lib/actions/dragdrop";
  import FolderItem from "./FolderItem.svelte";
  import CreateFolderDialog from "./CreateFolderDialog.svelte";
  import type { Snippet } from "svelte";

  type Props = {
    activeId?: string | null;
    children?: Snippet;
    onload?: (sessionId: string) => void;
  };

  let { activeId = null, children, onload }: Props = $props();

  /** True when dragging a folder (not a session) — shows insertion zones. */
  const isReordering = $derived(
    folderStore.isDragging && folderStore.dragPayload?.type === "folder",
  );

  // No local expandedFolders state — it's in the store now
</script>

<!-- Header -->
<div class="mb-2 flex items-center justify-between">
  <h2 class="text-xs font-semibold tracking-[0.16em] text-muted uppercase">Folders</h2>
  <button
    type="button"
    onclick={() => folderStore.openCreateDialog()}
    class="flex h-6 w-6 items-center justify-center rounded-md text-muted transition hover:bg-surface hover:text-ink"
    aria-label="Create folder"
    title="Create folder"
  >
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <path d="M7 3v8M3 7h8" />
    </svg>
  </button>
</div>

<!-- Error toast -->
{#if folderStore.error}
  <div
    class="mb-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-red-700"
    role="alert"
  >
    {folderStore.error}
  </div>
{/if}

<!-- Loading state -->
{#if folderStore.fetchState.status === "loading"}
  <div class="space-y-1.5">
    {#each [1, 2, 3] as i (i)}
      <div class="h-8 animate-pulse rounded-md bg-line"></div>
    {/each}
  </div>

  <!-- Error state -->
{:else if folderStore.fetchState.status === "error"}
  <p class="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">
    {folderStore.fetchState.message}
  </p>

  <!-- Empty state -->
{:else if folderStore.sortedFolders.length === 0}
  <p class="rounded-md border border-dashed border-line bg-surface p-3 text-sm text-muted">
    No folders yet. Create one to organize your sessions.
  </p>

  <!-- Folder list -->
{:else}
  <div class="flex flex-col">
    {#each folderStore.sortedFolders as folder (folder.id)}
      <!--
        Insertion zone BEFORE this folder.
        Always in DOM (no {#if}) to avoid DOM mutation during active drag.
        Hidden via CSS when not reordering.
      -->
      <div
        use:droppable={{
          target: { type: "reorder", id: folder.id, position: "before" },
          acceptTypes: ["folder"],
          ondragenter: (target) => folderStore.setDropTarget(target),
          ondragleave: () => {
            const dt = folderStore.dropTarget;
            if (dt?.id === folder.id && dt?.position === "before") {
              folderStore.setDropTarget(null);
            }
          },
          ondrop: async (payload, target) => {
            if (payload.type === "folder" && payload.id !== target.id) {
              await folderStore.reorder(payload.id, target.id, "before");
            }
            folderStore.endDrag();
          },
        }}
        class="reorder-zone"
        class:visible={isReordering}
        class:active={isReordering &&
          folderStore.dropTarget?.id === folder.id &&
          folderStore.dropTarget?.position === "before"}
      ></div>

      <!-- Folder with session drop zone -->
      <div
        use:droppable={{
          target: { type: "folder", id: folder.id },
          acceptTypes: ["session"],
          ondragenter: (target) => {
            // Only react to session drags — ignore folder reorder drags
            if (folderStore.dragPayload?.type === "session") {
              folderStore.setDropTarget(target);
            }
          },
          ondragleave: () => {
            if (folderStore.dropTarget?.id === folder.id && !folderStore.dropTarget?.position) {
              folderStore.setDropTarget(null);
            }
          },
          ondrop: async (payload, target) => {
            if (payload.type === "session" && target.type === "folder") {
              if (payload.sourceFolderId && payload.sourceFolderId !== target.id) {
                // Atomic move: single transaction, no intermediate orphan state
                await folderStore.moveSession(payload.sourceFolderId, target.id, payload.id);
              } else if (!payload.sourceFolderId) {
                // From history (not in any folder): just assign
                await folderStore.assignSession(target.id, payload.id);
              }
            }
            folderStore.endDrag();
          },
        }}
        class="folder-drop-zone"
        class:drag-over={folderStore.dropTarget?.id === folder.id &&
          !folderStore.dropTarget?.position}
      >
        <FolderItem folderId={folder.id} {activeId} onloadsession={onload} />
      </div>
    {/each}

    <!--
      Final insertion zone AFTER last folder.
      Always in DOM, hidden via CSS when not reordering.
    -->
    {#if folderStore.sortedFolders.length > 0}
      {@const lastFolder = folderStore.sortedFolders[folderStore.sortedFolders.length - 1]}
      <div
        use:droppable={{
          target: { type: "reorder", id: lastFolder.id, position: "after" },
          acceptTypes: ["folder"],
          ondragenter: (target) => folderStore.setDropTarget(target),
          ondragleave: () => {
            const dt = folderStore.dropTarget;
            if (dt?.id === lastFolder.id && dt?.position === "after") {
              folderStore.setDropTarget(null);
            }
          },
          ondrop: async (payload, target) => {
            if (payload.type === "folder" && payload.id !== target.id) {
              await folderStore.reorder(payload.id, target.id, "after");
            }
            folderStore.endDrag();
          },
        }}
        class="reorder-zone"
        class:visible={isReordering}
        class:active={isReordering &&
          folderStore.dropTarget?.id === lastFolder.id &&
          folderStore.dropTarget?.position === "after"}
      ></div>
    {/if}
  </div>
{/if}

<!-- Unorganized sessions slot -->
{#if children}
  <div class="mt-3 border-t border-line pt-2">
    <h3 class="mb-1 text-xs font-semibold tracking-[0.14em] text-muted uppercase">Unorganized</h3>
    {@render children()}
  </div>
{/if}

<!-- Create folder dialog -->
{#if folderStore.createDialogOpen}
  <CreateFolderDialog
    onclose={() => folderStore.closeCreateDialog()}
    oncreate={async (request) => {
      await folderStore.createFolder(request);
      folderStore.closeCreateDialog();
    }}
  />
{/if}

<style>
  .folder-drop-zone {
    border-radius: 6px;
    transition: background-color 150ms ease;
  }

  .folder-drop-zone.drag-over {
    background-color: color-mix(in srgb, var(--color-accent) 15%, transparent);
    outline: 2px dashed var(--color-accent);
    outline-offset: -2px;
  }

  /* ── Reorder insertion zones ──────────────────────────────────── */
  /* Always in DOM but collapsed by default (no hit area, no visual). */
  .reorder-zone {
    height: 0;
    padding: 0;
    pointer-events: none;
    border-radius: 2px;
    transition: all 120ms ease;
  }

  /* Visible state: 4px bar with 6px invisible hit padding. */
  .reorder-zone.visible {
    height: 4px;
    padding: 6px 0;
    pointer-events: auto;
  }

  /* Active state: accent-colored bar with glow. */
  .reorder-zone.active {
    background-color: var(--color-accent);
    background-clip: content-box;
    box-shadow: 0 0 8px color-mix(in srgb, var(--color-accent) 40%, transparent);
    border-radius: 3px;
  }
</style>

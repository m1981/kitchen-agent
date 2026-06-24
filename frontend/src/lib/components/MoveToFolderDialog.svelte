<script lang="ts">
  /**
   * MoveToFolderDialog
   * ==================
   * Dialog for moving a session to one or more folders with options for:
   * - Selecting target folders (multiple)
   * - Including children (if session is a fork parent)
   */

  import type { Folder } from "$lib/api";

  type Props = {
    open: boolean;
    sessionTitle: string;
    hasChildren: boolean;
    childrenCount: number;
    folders: Folder[];
    currentFolderIds: string[];
    onconfirm: (options: { folderIds: string[]; includeChildren: boolean }) => void;
    oncancel: () => void;
  };

  let {
    open,
    sessionTitle,
    hasChildren,
    childrenCount,
    folders,
    currentFolderIds,
    onconfirm,
    oncancel,
  }: Props = $props();

  let selectedFolders = $state(new Set<string>());
  let includeChildren = $state(false);

  // Initialize with current folders
  $effect(() => {
    if (open) {
      selectedFolders = new Set(currentFolderIds);
      includeChildren = false;
    }
  });

  function toggleFolder(folderId: string) {
    if (selectedFolders.has(folderId)) {
      selectedFolders.delete(folderId);
    } else {
      selectedFolders.add(folderId);
    }
    // Trigger reactivity
    selectedFolders = new Set(selectedFolders);
  }

  function handleConfirm() {
    onconfirm({
      folderIds: Array.from(selectedFolders),
      includeChildren,
    });
    selectedFolders = new Set();
    includeChildren = false;
  }

  function handleCancel() {
    oncancel();
    selectedFolders = new Set();
    includeChildren = false;
  }

  const hasChanges = $derived(
    selectedFolders.size !== currentFolderIds.length ||
      !currentFolderIds.every((id) => selectedFolders.has(id)),
  );
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    onclick={handleCancel}
  >
    <div
      class="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      onclick={(e) => e.stopPropagation()}
    >
      <h2 class="mb-4 text-xl font-semibold text-ink">Move to Folder</h2>

      <p class="mb-4 text-sm text-muted">
        Select folders for <strong>"{sessionTitle}"</strong>:
      </p>

      {#if folders.length === 0}
        <p class="mb-4 text-sm text-muted italic">No folders available. Create a folder first.</p>
      {:else}
        <div class="mb-4 max-h-48 space-y-2 overflow-y-auto">
          {#each folders as folder (folder.id)}
            <label class="flex items-center gap-2 rounded-md p-2 hover:bg-surface">
              <input
                type="checkbox"
                checked={selectedFolders.has(folder.id)}
                onchange={() => toggleFolder(folder.id)}
                class="h-4 w-4 rounded border-line text-accent focus:ring-accent"
              />
              <span class="text-sm">
                {folder.icon}
                {folder.name}
              </span>
            </label>
          {/each}
        </div>
      {/if}

      {#if hasChildren}
        <label class="mb-4 flex items-center gap-2">
          <input
            type="checkbox"
            bind:checked={includeChildren}
            class="h-4 w-4 rounded border-line text-accent focus:ring-accent"
          />
          <span class="text-sm text-ink">
            Also move {childrenCount} child session{childrenCount === 1 ? "" : "s"}
          </span>
        </label>
      {/if}

      <div class="flex justify-end gap-2">
        <button
          onclick={handleCancel}
          class="rounded-md border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-surface"
        >
          Cancel
        </button>
        <button
          onclick={handleConfirm}
          disabled={!hasChanges}
          class="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
        >
          Move
        </button>
      </div>
    </div>
  </div>
{/if}

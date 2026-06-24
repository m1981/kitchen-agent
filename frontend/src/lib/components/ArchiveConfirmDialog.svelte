<script lang="ts">
  /**
   * ArchiveConfirmDialog
   * ====================
   * Dialog for archiving a session with options for:
   * - Including children (if session is a fork parent)
   * - Removing from folder (if session is in a folder)
   */

  import ConfirmDialog from "./ConfirmDialog.svelte";

  type Props = {
    open: boolean;
    sessionTitle: string;
    hasChildren: boolean;
    childrenCount: number;
    isFoldered: boolean;
    folderName: string;
    onconfirm: (options: { includeChildren: boolean; removeFromFolder: boolean }) => void;
    oncancel: () => void;
  };

  let {
    open,
    sessionTitle,
    hasChildren,
    childrenCount,
    isFoldered,
    folderName,
    onconfirm,
    oncancel,
  }: Props = $props();

  let includeChildren = $state(false);
  let removeFromFolder = $state(false);

  function handleConfirm() {
    onconfirm({ includeChildren, removeFromFolder });
    // Reset state
    includeChildren = false;
    removeFromFolder = false;
  }

  function handleCancel() {
    oncancel();
    // Reset state
    includeChildren = false;
    removeFromFolder = false;
  }
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
      <h2 class="mb-4 text-xl font-semibold text-ink">Archive Session</h2>

      <p class="mb-4 text-sm text-muted">
        Are you sure you want to archive <strong>"{sessionTitle}"</strong>?
      </p>

      {#if isFoldered}
        <label class="mb-3 flex items-center gap-2">
          <input
            type="checkbox"
            bind:checked={removeFromFolder}
            class="h-4 w-4 rounded border-line text-accent focus:ring-accent"
          />
          <span class="text-sm text-ink">
            Remove from folder "{folderName}"
          </span>
        </label>
      {/if}

      {#if hasChildren}
        <label class="mb-4 flex items-center gap-2">
          <input
            type="checkbox"
            bind:checked={includeChildren}
            class="h-4 w-4 rounded border-line text-accent focus:ring-accent"
          />
          <span class="text-sm text-ink">
            Also archive {childrenCount} child session{childrenCount === 1 ? "" : "s"}
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
          class="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
        >
          Archive
        </button>
      </div>
    </div>
  </div>
{/if}

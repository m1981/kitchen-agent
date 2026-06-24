<script lang="ts">
  /**
   * SidebarLayout
   * =============
   * Composes the sidebar panels: FolderTree, SessionPanel, ArchivedPanel.
   *
   * Props:
   *   activeId — currently loaded session ID (for highlight).
   *   onload   — called when user clicks a session title.
   *   isStreaming — disables interactions during streaming.
   */
  import { folderStore } from "$lib/stores/folder.svelte";
  import FolderTree from "./FolderTree.svelte";
  import SessionPanel from "./SessionPanel.svelte";
  import ArchivedPanel from "./ArchivedPanel.svelte";

  type Props = {
    activeId: string | null;
    onload: (id: string) => void;
    isStreaming?: boolean;
  };

  let { activeId, onload, isStreaming = false }: Props = $props();

  // Initialize folder store on mount
  $effect(() => {
    folderStore.refresh();
  });
</script>

<div
  class="scrollbar-hidden flex min-h-0 flex-col overflow-y-auto pr-1 {isStreaming
    ? 'pointer-events-none opacity-50'
    : ''}"
>
  <!-- Folder tree -->
  <FolderTree {activeId} {onload}>
    <!-- Unorganized sessions will render below folders -->
  </FolderTree>

  <!-- Session forest -->
  <SessionPanel {activeId} {onload} {isStreaming} />

  <!-- Archived sessions -->
  <ArchivedPanel {activeId} {onload} />
</div>

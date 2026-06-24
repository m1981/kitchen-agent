<script lang="ts">
  import { draggable, type DraggableOptions } from "$lib/actions/dragdrop";
  import { folderStore } from "$lib/stores/folder.svelte";
  import type { Snippet } from "svelte";

  type Props = {
    sessionId: string;
    sessionTitle: string;
    /** When dragging from inside a folder, pass the source folder ID. */
    sourceFolderId?: string;
    children: Snippet;
  };

  let { sessionId, sessionTitle, sourceFolderId, children }: Props = $props();

  const dragOptions: DraggableOptions = $derived({
    payload: {
      type: "session",
      id: sessionId,
      title: sessionTitle,
      sourceFolderId,
    },
    ondragstart: (payload) => {
      console.debug("[DnD] DraggableSession.ondragstart", {
        id: payload.id,
        source: payload.sourceFolderId ?? "history",
      });
      folderStore.startDrag(payload);
    },
    ondragend: () => {
      console.debug("[DnD] DraggableSession.ondragend", { id: sessionId });
      folderStore.endDrag();
    },
  });
</script>

<div
  use:draggable={dragOptions}
  class="draggable-session"
  class:is-dragging={folderStore.dragPayload?.id === sessionId}
>
  {@render children()}
</div>

<style>
  .draggable-session {
    cursor: grab;
    transition: opacity 150ms ease;
  }

  .draggable-session:active {
    cursor: grabbing;
  }

  .draggable-session.is-dragging {
    opacity: 0.5;
  }

  :global(.dragging) {
    opacity: 0.5;
  }
</style>

/**
 * src/lib/actions/dragdrop.ts
 * ============================
 * Svelte 5 actions for HTML5 Drag and Drop.
 *
 * Usage:
 *   <div use:draggable={{ type: 'session', id: session.id, title: session.title }}>
 *   <div use:droppable={{ type: 'folder', id: folder.id }}>
 *
 * Design decisions:
 *   - Uses native HTML5 DnD API (no library dependency)
 *   - Custom drag image via dataTransfer
 *   - CSS classes for visual feedback (.dragging, .drag-over)
 *   - Actions communicate via callbacks, not store coupling
 */

import type { Action } from "svelte/action";
import type { DragPayload, DropTarget } from "$lib/types";

// ---------------------------------------------------------------------------
// Draggable action
// ---------------------------------------------------------------------------

export interface DraggableOptions {
  payload: DragPayload;
  ondragstart?: (payload: DragPayload) => void;
  ondragend?: () => void;
}

export const draggable: Action<HTMLElement, DraggableOptions> = (node, options) => {
  let currentOptions = options;

  function handleDragStart(e: DragEvent) {
    if (!e.dataTransfer || !currentOptions) return;

    console.debug("[DnD] dragstart", currentOptions.payload);

    // Set drag data
    e.dataTransfer.setData("application/json", JSON.stringify(currentOptions.payload));
    e.dataTransfer.effectAllowed = "move";

    // Visual feedback
    node.classList.add("dragging");

    // Custom drag image (optional)
    const dragImage = document.createElement("div");
    dragImage.textContent = currentOptions.payload.title;
    dragImage.className = "drag-ghost";
    dragImage.style.cssText =
      "position: absolute; top: -1000px; padding: 4px 8px; background: var(--color-surface); border: 1px solid var(--color-line); border-radius: 4px; font-size: 12px;";
    document.body.appendChild(dragImage);
    e.dataTransfer.setDragImage(dragImage, 0, 0);

    // Cleanup ghost after drag starts
    requestAnimationFrame(() => {
      document.body.removeChild(dragImage);
    });

    currentOptions.ondragstart?.(currentOptions.payload);
  }

  function handleDragEnd() {
    console.debug("[DnD] dragend", currentOptions?.payload?.id);
    node.classList.remove("dragging");
    currentOptions.ondragend?.();
  }

  node.setAttribute("draggable", "true");
  node.addEventListener("dragstart", handleDragStart);
  node.addEventListener("dragend", handleDragEnd);

  return {
    update(newOptions) {
      currentOptions = newOptions;
    },
    destroy() {
      node.removeAttribute("draggable");
      node.removeEventListener("dragstart", handleDragStart);
      node.removeEventListener("dragend", handleDragEnd);
    },
  };
};

// ---------------------------------------------------------------------------
// Droppable action
// ---------------------------------------------------------------------------

export interface DroppableOptions {
  target: DropTarget;
  ondragenter?: (target: DropTarget) => void;
  ondragleave?: () => void;
  ondrop?: (payload: DragPayload, target: DropTarget) => void;
  acceptTypes?: ("session" | "folder")[];
}

export const droppable: Action<HTMLElement, DroppableOptions> = (node, options) => {
  let currentOptions = options;
  let dragCounter = 0; // Track enter/leave for nested elements

  function isValidDrop(payload: DragPayload): boolean {
    if (!currentOptions?.acceptTypes) return true;
    return currentOptions.acceptTypes.includes(payload.type);
  }

  function handleDragEnter(e: DragEvent) {
    e.preventDefault();
    dragCounter++;

    if (dragCounter === 1) {
      console.debug(
        "[DnD] dragenter →",
        currentOptions?.target,
        "payload:",
        e.dataTransfer ? "present" : "none",
      );
      node.classList.add("drag-over");
      currentOptions?.ondragenter?.(currentOptions.target);
    }
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "move";
    }
  }

  function handleDragLeave() {
    dragCounter--;
    if (dragCounter === 0) {
      console.debug("[DnD] dragleave ←", currentOptions?.target);
      node.classList.remove("drag-over");
      currentOptions?.ondragleave?.();
    }
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragCounter = 0;
    node.classList.remove("drag-over");

    if (!e.dataTransfer) {
      console.debug("[DnD] drop (no dataTransfer) on", currentOptions?.target);
      return;
    }

    try {
      const data = JSON.parse(e.dataTransfer.getData("application/json")) as DragPayload;
      console.debug("[DnD] drop", {
        payload: data,
        target: currentOptions?.target,
        valid: isValidDrop(data),
      });
      if (isValidDrop(data)) {
        currentOptions?.ondrop?.(data, currentOptions.target);
      }
    } catch (err) {
      console.debug("[DnD] drop (invalid JSON)", err);
    }
  }

  node.addEventListener("dragenter", handleDragEnter);
  node.addEventListener("dragover", handleDragOver);
  node.addEventListener("dragleave", handleDragLeave);
  node.addEventListener("drop", handleDrop);

  return {
    update(newOptions) {
      currentOptions = newOptions;
    },
    destroy() {
      node.removeEventListener("dragenter", handleDragEnter);
      node.removeEventListener("dragover", handleDragOver);
      node.removeEventListener("dragleave", handleDragLeave);
      node.removeEventListener("drop", handleDrop);
    },
  };
};

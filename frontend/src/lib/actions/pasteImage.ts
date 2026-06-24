/**
 * lib/actions/pasteImage.ts
 * ==========================
 * Svelte Action — attaches a `paste` event listener to any element and
 * extracts the first image from the clipboard, firing a callback with the
 * parsed PastedImage data.
 *
 * Extracted from +page.svelte to follow the "Actions" pattern: DOM glue
 * belongs in a reusable action, not scattered in component event handlers.
 *
 * Usage:
 *   import { pasteImage } from '$lib/actions/pasteImage';
 *   import { chatStore } from '$lib/stores/chat.svelte';
 *
 *   <textarea use:pasteImage={chatStore.addPastedImage}></textarea>
 */

import type { Action } from "svelte/action";
import type { PastedImage } from "$lib/types";

export const pasteImage: Action<HTMLElement, (img: PastedImage) => void> = (
  node,
  onImagePasted,
) => {
  function handlePaste(event: ClipboardEvent) {
    const items = event.clipboardData?.items;
    if (!items) return;

    for (const item of Array.from(items)) {
      if (!item.type.startsWith("image/")) continue;
      event.preventDefault();

      const file = item.getAsFile();
      if (!file) continue;

      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        const [header, base64] = dataUrl.split(",");
        const mimeType = header.split(":")[1].split(";")[0];
        onImagePasted({ dataUrl, mimeType, base64 });
      };
      reader.readAsDataURL(file);
    }
  }

  node.addEventListener("paste", handlePaste);

  return {
    // Called when the parameter changes (e.g. the callback reference changes).
    update(newCallback: (img: PastedImage) => void) {
      onImagePasted = newCallback;
    },
    destroy() {
      node.removeEventListener("paste", handlePaste);
    },
  };
};

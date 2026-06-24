/**
 * lib/actions/textSelection.ts
 * =============================
 * Svelte Action — attaches a `mouseup` listener to a container element and
 * classifies every text-selection event into one of two outcomes:
 *
 *   1. Selection inside a `[data-chat-bubble]` element  → `onchatselect`
 *   2. Selection cleared / too short / outside bubble   → `onchatselect(null)`
 *
 * Design goals:
 *   - Zero Svelte imports — pure TypeScript DOM glue.
 *   - All geometry helpers live here so +page.svelte has none.
 *   - The action returns an `update()` so callbacks can be hot-swapped
 *     when the component re-renders (required by Svelte's action contract).
 *
 * Usage:
 *   import { textSelection } from '$lib/actions/textSelection';
 *
 *   <div use:textSelection={{
 *     onchatselect: (hit) => notePopup = hit,  // null to clear
 *   }}>
 *     …page content…
 *   </div>
 *
 * Type exported so callers can annotate their $state variables:
 *   ChatSelectionHit  — position + text + bubble role
 */

import type { Action } from "svelte/action";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type ChatSelectionHit = {
  text: string;
  sourceRole: "user" | "assistant";
  x: number;
  y: number;
};

export type TextSelectionParams = {
  onchatselect: (hit: ChatSelectionHit | null) => void;
  /** Minimum character count before a selection is considered intentional. Default: 5 */
  minLength?: number;
};

// ---------------------------------------------------------------------------
// Internal helpers — all geometry lives here, not in the component
// ---------------------------------------------------------------------------

/**
 * Clamp a floating popup so it stays inside the viewport.
 * `width` / `height` are the popup's expected dimensions (used for clamping).
 */
function popupPosition(event: MouseEvent, width: number, height: number): { x: number; y: number } {
  const gap = 12;
  return {
    x: Math.min(Math.max(event.clientX, gap), window.innerWidth - width - gap),
    y: Math.min(Math.max(event.clientY - 48, gap), window.innerHeight - height - gap),
  };
}

/** Walk up from a text Node to its nearest HTMLElement. */
function toElement(node: Node | null): HTMLElement | null {
  if (!node) return null;
  return node instanceof HTMLElement ? node : node.parentElement;
}

/**
 * Returns the chat-bubble hit if the current window selection sits entirely
 * inside a single `[data-chat-bubble]` element with a valid role attribute.
 * Returns `null` for cross-bubble, non-bubble, or too-short selections.
 */
function readChatSelection(event: MouseEvent, minLength: number): ChatSelectionHit | null {
  const selection = window.getSelection();
  const text = selection?.toString().trim() ?? "";
  if (!selection || selection.rangeCount === 0 || text.length < minLength) return null;

  const anchorBubble = toElement(selection.anchorNode)?.closest<HTMLElement>("[data-chat-bubble]");
  const focusBubble = toElement(selection.focusNode)?.closest<HTMLElement>("[data-chat-bubble]");

  // Must be within a bubble, and both endpoints in the same bubble.
  const bubble = anchorBubble ?? focusBubble;
  if (!bubble) return null;
  if (anchorBubble && focusBubble && anchorBubble !== focusBubble) return null;

  const role = bubble.dataset.chatBubble;
  if (role !== "user" && role !== "assistant") return null;

  const { x, y } = popupPosition(event, 288, 220);
  return { text, sourceRole: role, x, y };
}

// ---------------------------------------------------------------------------
// The action
// ---------------------------------------------------------------------------

export const textSelection: Action<HTMLElement, TextSelectionParams> = (node, params) => {
  let { onchatselect, minLength = 5 } = params;

  /**
   * Track whether the *next* click-away should be suppressed.
   * When a popup appears on mouseup, the same event also bubbles up
   * as a "click" on the root container — which would immediately dismiss
   * the popup we just opened. We eat that first click here.
   */
  let suppressNextClick = false;

  function handleMouseUp(event: MouseEvent) {
    const target = event.target as HTMLElement;

    // Never trigger when the user clicks interactive elements or the note popup.
    if (target.closest("button, input, textarea, select, .note-popup")) return;

    const chatHit = readChatSelection(event, minLength);
    if (chatHit) {
      onchatselect(chatHit);
      suppressNextClick = true;
      return;
    }

    // Nothing relevant selected — clear popup.
    onchatselect(null);
  }

  function handleClick(event: MouseEvent) {
    if (suppressNextClick) {
      suppressNextClick = false;
      return;
    }
    // Click-away: dismiss the note popup when clicking outside it.
    const t = event.target as HTMLElement;
    if (!t.closest(".note-popup")) onchatselect(null);
  }

  node.addEventListener("mouseup", handleMouseUp);
  node.addEventListener("click", handleClick);

  return {
    update(newParams: TextSelectionParams) {
      onchatselect = newParams.onchatselect;
      minLength = newParams.minLength ?? 5;
    },
    destroy() {
      node.removeEventListener("mouseup", handleMouseUp);
      node.removeEventListener("click", handleClick);
    },
  };
};

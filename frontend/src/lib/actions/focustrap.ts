/**
 * src/lib/actions/focustrap.ts
 * =============================
 * Svelte action that traps keyboard focus inside a floating element
 * (popup, modal, context menu).
 *
 * Usage:
 *   <div use:focusTrap>…</div>
 */

import type { Action } from "svelte/action";

const FOCUSABLE =
  "a[href], button:not([disabled]), input:not([disabled]), " +
  "textarea:not([disabled]), select:not([disabled]), " +
  '[tabindex]:not([tabindex="-1"])';

export const focusTrap: Action<HTMLElement> = (node) => {
  // Auto-focus the first focusable child when the element mounts.
  const firstFocusable = node.querySelector<HTMLElement>(FOCUSABLE);
  firstFocusable?.focus();

  function handleKeydown(e: KeyboardEvent) {
    if (e.key !== "Tab") return;

    const focusable = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => !el.closest("[disabled]"),
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  node.addEventListener("keydown", handleKeydown);
  return {
    destroy() {
      node.removeEventListener("keydown", handleKeydown);
    },
  };
};

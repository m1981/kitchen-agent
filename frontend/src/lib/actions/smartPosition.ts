/**
 * smartPosition — Svelte action for intelligent dropdown/popover positioning.
 *
 * Uses @floating-ui/dom to flip, shift, and offset the floating element
 * so it always stays within the viewport.
 *
 * Usage:
 *   <div use:smartPosition={{ trigger: triggerEl, placement: 'bottom-end' }}>
 *     ...menu items...
 *   </div>
 *
 * The action automatically repositions on scroll/resize and cleans up on destroy.
 */

import type { Action } from "svelte";
import { computePosition, flip, shift, offset, type Placement } from "@floating-ui/dom";

type SmartPositionOptions = {
  trigger: HTMLElement;
  placement?: Placement;
  gap?: number;
  padding?: number;
};

export const smartPosition: Action<HTMLElement, SmartPositionOptions> = (
  node,
  { trigger, placement = "bottom-start", gap = 4, padding = 8 },
) => {
  let rafId: number | null = null;

  function update() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(() => {
      computePosition(trigger, node, {
        placement,
        middleware: [offset(gap), flip({ padding }), shift({ padding })],
      }).then(({ x, y }) => {
        node.style.left = `${x}px`;
        node.style.top = `${y}px`;
      });
    });
  }

  // Initial positioning
  update();

  // Reposition on scroll (capture phase for nested scroll containers) and resize
  window.addEventListener("scroll", update, true);
  window.addEventListener("resize", update);

  return {
    update({ trigger: newTrigger, placement: newPlacement, gap: newGap, padding: newPadding }) {
      trigger = newTrigger;
      placement = newPlacement ?? placement;
      gap = newGap ?? gap;
      padding = newPadding ?? padding;
      update();
    },
    destroy() {
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    },
  };
};

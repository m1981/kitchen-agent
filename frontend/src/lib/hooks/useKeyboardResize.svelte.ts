/**
 * lib/hooks/useKeyboardResize.svelte.ts
 * =======================================
 * Rune-based hook that encapsulates keyboard-driven resize logic for the
 * three resizable areas: left sidebar, right sidebar, and prompt composer.
 *
 * Why a hook and not an action?
 *   Keyboard resize needs access to the *sidebarResize* store instance so it
 *   can call `resizeLeftBy`, `resizeRightBy`, `resizePromptBy`, etc.
 *   That store reference is passed in at call-site, so the hook is just a
 *   plain factory function — no DOM element needed, nothing to `destroy`.
 *
 * Usage:
 *   import { createKeyboardResize } from '$lib/hooks/useKeyboardResize.svelte';
 *   const kbResize = createKeyboardResize(sidebarResize);
 *
 *   <button onkeydown={(e) => kbResize.sidebar(e, 'left')}  …>
 *   <button onkeydown={(e) => kbResize.sidebar(e, 'right')} …>
 *   <button onkeydown={kbResize.prompt}                     …>
 */

type SidebarResizeStore = {
  resizeLeftBy(delta: number): void;
  resizeRightBy(delta: number): void;
  resizePromptBy(delta: number): void;
  resetLeft(): void;
  resetRight(): void;
  resetPrompt(): void;
};

export function createKeyboardResize(store: SidebarResizeStore) {
  /**
   * Handle ArrowLeft / ArrowRight / Home on a sidebar drag-handle button.
   * Shift multiplies the step by 2.5× for coarse adjustment.
   *
   * @param event  — the keydown event from the button element
   * @param side   — which sidebar is being resized
   */
  function sidebar(event: KeyboardEvent, side: "left" | "right"): void {
    if (!["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) return;
    event.preventDefault();

    const step = event.shiftKey ? 40 : 16;

    if (event.key === "Home") {
      side === "left" ? store.resetLeft() : store.resetRight();
      return;
    }

    const direction = event.key === "ArrowRight" ? 1 : -1;
    if (side === "left") {
      store.resizeLeftBy(direction * step);
    } else {
      // Right sidebar grows leftward, so the delta is inverted.
      store.resizeRightBy(direction * -step);
    }
  }

  /**
   * Handle ArrowUp / ArrowDown / Home on the prompt composer resize handle.
   * Shift multiplies the step by 2.5× for coarse adjustment.
   *
   * @param event — the keydown event from the handle button element
   */
  function prompt(event: KeyboardEvent): void {
    if (!["ArrowUp", "ArrowDown", "Home"].includes(event.key)) return;
    event.preventDefault();

    const step = event.shiftKey ? 40 : 16;

    if (event.key === "Home") {
      store.resetPrompt();
      return;
    }

    store.resizePromptBy(event.key === "ArrowUp" ? step : -step);
  }

  return { sidebar, prompt } as const;
}

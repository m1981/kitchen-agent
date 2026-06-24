<script lang="ts">
  /**
   * ConfirmDialog
   * ==============
   * Accessible modal confirmation dialog.
   * Replaces native window.confirm() for testability.
   *
   * Auto-confirm mode:
   *   Set window.__testHelpers.autoConfirm = true to auto-accept all dialogs.
   *   Used by browser-test.js --auto-confirm flag.
   *
   * Props:
   *   message    — the question to display
   *   onconfirm  — called when user confirms
   *   oncancel   — called when user cancels
   */

  import { onMount } from "svelte";
  import Dialog from "./ui/Dialog.svelte";

  type Props = {
    message: string;
    onconfirm: () => void;
    oncancel: () => void;
  };

  let { message, onconfirm, oncancel }: Props = $props();

  // Auto-confirm mode for E2E tests
  onMount(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const helpers = (window as any).__testHelpers;
    if (helpers?.autoConfirm) {
      requestAnimationFrame(() => onconfirm());
    }
  });
</script>

<Dialog open={true} onclose={oncancel} title="Confirm">
  <p class="text-sm text-ink">{message}</p>

  {#snippet footer()}
    <button
      onclick={oncancel}
      data-testid="confirm-cancel"
      class="rounded-md border border-line px-3 py-1.5 text-sm font-medium text-muted transition hover:bg-surface focus:ring-2 focus:ring-accent focus:outline-none"
    >
      Cancel
    </button>
    <button
      onclick={onconfirm}
      data-testid="confirm-ok"
      class="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-red-700 focus:ring-2 focus:ring-red-500 focus:outline-none"
    >
      Confirm
    </button>
  {/snippet}
</Dialog>

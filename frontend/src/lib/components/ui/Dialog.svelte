<script lang="ts">
  /**
   * Dialog
   * ======
   * Shared modal dialog component with:
   *   - Escape key handling
   *   - Backdrop click to close
   *   - Title, children, and footer slots
   *   - Body scroll lock
   *
   * Usage:
   *   <Dialog open={showDialog} onclose={() => show = false} title="Confirm">
   *     <p>Are you sure?</p>
   *     {#snippet footer()}
   *       <button onclick={() => show = false}>Cancel</button>
   *       <button onclick={handleConfirm}>Confirm</button>
   *     {/snippet}
   *   </Dialog>
   */
  import type { Snippet } from "svelte";

  type Props = {
    open: boolean;
    onclose: () => void;
    title?: string;
    children: Snippet;
    footer?: Snippet;
  };

  let { open, onclose, title, children, footer }: Props = $props();

  let dialogEl = $state<HTMLDivElement | null>(null);

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onclose();
    }
  }

  function handleBackdropClick(e: MouseEvent) {
    if (e.target === e.currentTarget) {
      onclose();
    }
  }

  // Lock body scroll when dialog is open
  $effect(() => {
    if (open) {
      const original = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = original;
      };
    }
  });
</script>

{#if open}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    onclick={handleBackdropClick}
    onkeydown={handleKeydown}
    role="dialog"
    tabindex="-1"
    aria-modal="true"
    aria-label={title ?? "Dialog"}
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      bind:this={dialogEl}
      class="mx-4 w-full max-w-md rounded-xl bg-surface p-6 shadow-xl"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      {#if title}
        <h2 class="mb-4 text-xl font-semibold text-ink">{title}</h2>
      {/if}

      {@render children()}

      {#if footer}
        <div class="mt-4 flex justify-end gap-3">
          {@render footer()}
        </div>
      {/if}
    </div>
  </div>
{/if}

<script lang="ts">
  /**
   * +error.svelte
   * =============
   * SvelteKit error page for the chat route.
   * Shows when a route error occurs (e.g., invalid session ID).
   */
  import { page } from "$app/stores";
</script>

<div class="flex min-h-screen items-center justify-center bg-surface">
  <div class="mx-auto max-w-md px-4 text-center">
    <div class="mb-6 text-6xl">⚠️</div>
    <h1 class="mb-2 text-xl font-bold text-ink">Something went wrong</h1>
    <p class="mb-6 text-muted">
      {$page.error?.message ?? "An unexpected error occurred"}
    </p>
    <div class="flex justify-center gap-4">
      <a
        href="/chat/{crypto.randomUUID()}"
        class="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent/90"
      >
        Start new chat
      </a>
      <button
        onclick={() => history.back()}
        class="rounded-md border border-line px-4 py-2 text-sm text-ink transition hover:bg-surface"
      >
        Go back
      </button>
    </div>
  </div>
</div>

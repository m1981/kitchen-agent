<script lang="ts">
  /**
   * +page.svelte — Root redirect
   * =============================
   * This page exists only to redirect `/` to `/chat/{uuid}`.
   * The actual chat UI lives at /chat/[id]/+page.svelte.
   */

  import { onMount } from "svelte";
  import { goto } from "$app/navigation";

  onMount(() => {
    const newId = crypto.randomUUID();
    goto(`/chat/${newId}`, { replaceState: true });
  });
</script>

<!-- Brief loading state while redirecting -->
<div class="flex h-screen items-center justify-center bg-surface text-muted">
  <p class="text-sm">Loading...</p>
</div>

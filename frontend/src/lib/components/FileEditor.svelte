<script lang="ts">
  /**
   * FileEditor – inline Markdown editor for a single knowledge-base file.
   *
   * Fetches content via api.readFile, saves via api.writeFile.
   * Calls onclose() when the user clicks ✕.
   * Calls onsave()  after a successful save (so the parent can refresh lists).
   */

  import { api } from "$lib/api";

  type Props = {
    filepath: string;
    onclose: () => void;
    onsave?: () => void;
  };

  let { filepath, onclose, onsave }: Props = $props();

  // ── State ────────────────────────────────────────────────────────────────
  let content = $state("");
  let original = $state("");
  let loading = $state(true);
  let saving = $state(false);
  let error = $state("");
  let saved = $state(false);

  const isDirty = $derived(content !== original);

  // ── Load on filepath change ───────────────────────────────────────────────
  $effect(() => {
    if (!filepath) return;
    loading = true;
    error = "";
    saved = false;

    api
      .readFile(filepath)
      .then((data) => {
        content = data.content;
        original = data.content;
      })
      .catch((e: unknown) => (error = String(e)))
      .finally(() => (loading = false));
  });

  // ── Save ─────────────────────────────────────────────────────────────────
  async function save() {
    saving = true;
    error = "";
    saved = false;
    try {
      await api.writeFile(filepath, content);
      original = content;
      saved = true;
      onsave?.();
      setTimeout(() => (saved = false), 2000);
    } catch (e: unknown) {
      error = String(e);
    } finally {
      saving = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "s") {
      e.preventDefault();
      save();
    }
  }
</script>

<div class="flex h-full flex-col">
  <!-- Header -->
  <div class="flex items-center justify-between border-b border-line px-3 py-2">
    <div class="min-w-0">
      <p class="truncate text-xs font-semibold text-ink" title={filepath}>{filepath}</p>
      {#if isDirty}
        <span class="text-xs text-accent">● unsaved</span>
      {:else if saved}
        <span class="text-xs text-green-600">✓ saved</span>
      {/if}
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <button
        onclick={save}
        disabled={saving || !isDirty}
        class="rounded bg-accent px-2.5 py-1 text-xs font-semibold text-white transition hover:bg-accent-strong disabled:opacity-40"
      >
        {saving ? "Saving…" : "⌘S Save"}
      </button>
      <button
        onclick={onclose}
        class="rounded px-2 py-1 text-xs font-medium text-muted transition hover:text-ink"
        aria-label="Close editor"
      >
        ✕
      </button>
    </div>
  </div>

  {#if error}
    <p class="bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>
  {/if}

  {#if loading}
    <div class="flex flex-1 items-center justify-center text-sm text-muted">Loading…</div>
  {:else}
    <textarea
      class="flex-1 resize-none bg-surface p-3 font-mono text-xs leading-5 text-ink focus:outline-none"
      bind:value={content}
      onkeydown={handleKeydown}
      spellcheck={false}
    ></textarea>
  {/if}
</div>

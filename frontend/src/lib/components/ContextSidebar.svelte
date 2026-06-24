<script lang="ts">
  /**
   * ContextSidebar – right panel with two tabs:
   *   1. "Context" – select files to inject as context into the next message
   *   2. "Editor"  – inline Markdown editor for the selected file
   *
   * Props:
   *   checkedFiles             – set of currently checked file paths (driven
   *                              by the parent / store so it clears after send)
   *   oncontextchange(paths)   – emitted when the selection changes
   *   oninsertnotes(notes)     – emitted when user inserts notes into composer
   *   sessionId                – current session ID (for notes tab)
   */

  import { SvelteSet } from "svelte/reactivity";
  import { api, type FileItem, type Note } from "$lib/api";
  import FileEditor from "./FileEditor.svelte";
  import NotesPanel from "./NotesPanel.svelte";

  type Props = {
    checkedFiles: string[];
    oncontextchange: (paths: string[]) => void;
    oninsertnotes: (notes: Note[]) => void;
    sessionId: string;
  };

  let { checkedFiles, oncontextchange, oninsertnotes, sessionId }: Props = $props();

  // ── State ────────────────────────────────────────────────────────────────
  let files = $state<FileItem[]>([]);
  let editingFile = $state<string | null>(null);
  let loading = $state(true);
  let tab = $state<"context" | "editor" | "notes">("context");

  // Derive the checked set from the prop so it clears when the store clears.
  const selectedPaths = $derived(new Set(checkedFiles));

  // ── Load files ───────────────────────────────────────────────────────────
  $effect(() => {
    api
      .listFiles()
      .then((data) => (files = data))
      .catch(() => {})
      .finally(() => (loading = false));
  });

  // ── Handlers ─────────────────────────────────────────────────────────────
  function toggleFile(path: string) {
    const next = new SvelteSet(selectedPaths);
    if (next.has(path)) {
      next.delete(path);
    } else {
      next.add(path);
    }
    oncontextchange(Array.from(next));
  }

  function openEditor(path: string) {
    editingFile = path;
    tab = "editor";
  }

  function closeEditor() {
    editingFile = null;
    tab = "context";
  }

  function refreshFiles() {
    api
      .listFiles()
      .then((data) => (files = data))
      .catch(() => {});
  }
</script>

<aside class="flex h-full w-full shrink-0 flex-col border-l border-line bg-panel/90">
  <!-- Tab bar -->
  <div class="flex border-b border-line">
    <button
      onclick={() => (tab = "context")}
      class="flex-1 py-2 text-xs font-semibold transition {tab === 'context'
        ? 'border-b-2 border-accent text-accent'
        : 'text-muted hover:text-ink'}"
    >
      📎 Context
    </button>
    <button
      onclick={() => (tab = "notes")}
      class="flex-1 py-2 text-xs font-semibold transition {tab === 'notes'
        ? 'border-b-2 border-accent text-accent'
        : 'text-muted hover:text-ink'}"
    >
      📌 Notes
    </button>
    <button
      onclick={() => (tab = "editor")}
      class="flex-1 py-2 text-xs font-semibold transition {tab === 'editor'
        ? 'border-b-2 border-accent text-accent'
        : 'text-muted hover:text-ink'}"
    >
      ✏️ Editor
    </button>
  </div>

  <!-- Context tab -->
  {#if tab === "context"}
    <div class="flex flex-col overflow-hidden p-3">
      <p class="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">
        Inject into next message
      </p>
      <p class="mb-3 text-xs leading-4 text-muted">
        Tick files to add their full content to the context window before sending your next message.
      </p>

      {#if loading}
        <p class="text-xs text-muted">Loading files…</p>
      {:else if files.length === 0}
        <p class="rounded border border-dashed border-line p-3 text-xs text-muted">
          No markdown files found in data/.
        </p>
      {:else}
        <ul class="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {#each files as file (file.path)}
            <li class="flex items-center gap-1 rounded-md px-1 py-1 hover:bg-surface">
              <input
                type="checkbox"
                id="ctx-{file.path}"
                checked={selectedPaths.has(file.path)}
                onchange={() => toggleFile(file.path)}
                class="h-3.5 w-3.5 accent-accent"
              />
              <label
                for="ctx-{file.path}"
                class="min-w-0 flex-1 cursor-pointer truncate text-xs text-ink"
                title={file.path}
              >
                {file.name}
              </label>
              <button
                onclick={() => openEditor(file.path)}
                class="shrink-0 rounded px-1.5 py-0.5 text-xs text-muted transition hover:bg-line hover:text-ink"
                title="Open in editor"
              >
                ✏️
              </button>
            </li>
          {/each}
        </ul>
      {/if}

      {#if selectedPaths.size > 0}
        <div class="mt-3 rounded-md border border-accent-soft bg-accent-soft px-2 py-1.5">
          <p class="text-xs font-medium text-accent">
            {selectedPaths.size} file{selectedPaths.size > 1 ? "s" : ""} will be injected
          </p>
        </div>
      {/if}
    </div>

    <!-- Notes tab -->
  {:else if tab === "notes"}
    <NotesPanel {sessionId} {oninsertnotes} />

    <!-- Editor tab -->
  {:else if tab === "editor"}
    <div class="flex flex-1 flex-col overflow-hidden">
      {#if !editingFile}
        <div class="p-3">
          <p class="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Open a file</p>
          {#if loading}
            <p class="text-xs text-muted">Loading…</p>
          {:else}
            <ul class="space-y-1">
              {#each files as file (file.path)}
                <li>
                  <button
                    onclick={() => openEditor(file.path)}
                    class="w-full rounded-md px-2 py-1.5 text-left text-xs text-ink transition hover:bg-surface"
                    title={file.path}
                  >
                    {file.name}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {:else}
        <FileEditor filepath={editingFile} onclose={closeEditor} onsave={refreshFiles} />
      {/if}
    </div>
  {/if}
</aside>

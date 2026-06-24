<script lang="ts">
  /**
   * /chat/[id]/+page.svelte — Kitchen Agent
   * =========================================
   * URL-driven chat session page.
   *
   * The session ID comes from `$page.params.id` and is the single source
   * of truth. This enables:
   *   - Browser refresh preserves the current session
   *   - Back/forward navigation works correctly
   *   - Direct URL linking to specific sessions
   *
   * Lifecycle:
   *   1. $effect watches `$page.params.id`
   *   2. Calls `chatStore.loadSession(id)` which handles 404 gracefully
   *   3. If session doesn't exist, shows empty chat (ready for first message)
   */

  import { onMount } from "svelte";
  import { goto, beforeNavigate } from "$app/navigation";
  import { page } from "$app/stores";

  import { chatStore } from "$lib/stores/chat.svelte";
  import { providerStore } from "$lib/stores/provider.svelte";
  import { promptStore } from "$lib/stores/prompt.svelte";
  import { editorStore } from "$lib/stores/editor.svelte";
  import { sessionStore } from "$lib/stores/sessions.svelte";
  import { createSidebarResize } from "$lib/sidebar-resize.svelte";
  import { textSelection } from "$lib/actions/textSelection";
  import { createKeyboardResize } from "$lib/hooks/useKeyboardResize.svelte";

  import { api, type PromptMode, type Note } from "$lib/api";
  import type { ChatSelectionHit } from "$lib/actions/textSelection";

  import ChatHeader from "$lib/components/ChatHeader.svelte";
  import ChatMessageList from "$lib/components/ChatMessageList.svelte";
  import ChatComposer from "$lib/components/ChatComposer.svelte";
  import SidebarLayout from "$lib/components/SidebarLayout.svelte";
  import ContextSidebar from "$lib/components/ContextSidebar.svelte";
  import NotePopup from "$lib/components/NotePopup.svelte";

  // ---------------------------------------------------------------------------
  // Layout resize
  // ---------------------------------------------------------------------------

  const sidebarResize = createSidebarResize();
  const kbResize = createKeyboardResize(sidebarResize);

  // ---------------------------------------------------------------------------
  // Prompt mode list — fetched once on mount; selectedModeId lives in chatStore
  // ---------------------------------------------------------------------------

  let modes = $state<PromptMode[]>([]);

  // ---------------------------------------------------------------------------
  // Note popup state — set by the textSelection action callback
  // ---------------------------------------------------------------------------

  let notePopup = $state<ChatSelectionHit | null>(null);

  // ---------------------------------------------------------------------------
  // Composer — bind:currentMessage so notes can be injected from the sidebar
  // ---------------------------------------------------------------------------

  let currentMessage = $state("");
  let textareaEl = $state<HTMLTextAreaElement | null>(null);

  // ---------------------------------------------------------------------------
  // Derived — active mode label / icon resolved from the live modes list
  // ---------------------------------------------------------------------------

  const activeMode = $derived(
    modes.find((m) => m.id === promptStore.selectedModeId) ?? {
      id: promptStore.selectedModeId,
      label: promptStore.selectedModeId,
      eyebrow: "",
    },
  );

  // Derived: true when the session has a non-empty system prompt override.
  const hasSystemPromptOverride = $derived(editorStore.isSystemPromptOverride);

  // Resolved system prompt text: override ?? mode default
  const systemPromptText = $derived(editorStore.resolvedSystemPrompt);

  // Derived: edit state helpers
  const isEditSaving = $derived(editorStore.editState.status === "loading");
  const editError = $derived(
    editorStore.editState.status === "error" ? editorStore.editState.message : "",
  );

  // ---------------------------------------------------------------------------
  // Busy-recent indicator — stays true for 300ms after operation completes
  // Allows E2E tests to observe the loading state before optimistic updates
  // ---------------------------------------------------------------------------

  let busyRecent = $state(false);
  let busyTimer: ReturnType<typeof setTimeout> | undefined;

  // ── Page loading state ────────────────────────────────────────────────────
  let pageReady = $state(false);

  $effect(() => {
    const isBusy =
      editorStore.editState.status === "loading" || chatStore.chatState.status === "loading";
    if (isBusy) {
      busyRecent = true;
      if (busyTimer) clearTimeout(busyTimer);
    } else if (busyRecent) {
      busyTimer = setTimeout(() => {
        busyRecent = false;
      }, 300);
    }
  });

  // ---------------------------------------------------------------------------
  // URL-driven session loading — THE KEY CHANGE
  // ---------------------------------------------------------------------------

  // Track the current URL param to avoid redundant loads
  let lastLoadedId = $state<string | null>(null);

  // Derived: current session ID from URL (guaranteed to exist for this route)
  const currentSessionId = $derived($page.params.id ?? "");

  // Session title from the session store (null if new/unknown session)
  const sessionTitle = $derived(sessionStore.getTitleById(currentSessionId));

  $effect(() => {
    const id = currentSessionId;

    // Skip if empty or already loaded
    if (!id || id === lastLoadedId) return;
    lastLoadedId = id;
    pageReady = false;

    // Load session — handles 404 gracefully (treats as new chat)
    chatStore.loadSession(id).then(() => {
      pageReady = true;
    });
    sessionStore.setActive(id);
  });

  // ---------------------------------------------------------------------------
  // Bootstrap — load modes and providers in parallel on mount
  // ---------------------------------------------------------------------------

  onMount(async () => {
    void sessionStore.refresh();

    // Expose stores and test helpers on window for browser-based testing (dev mode only)
    if (import.meta.env.DEV) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- dev-only test helpers
      (window as any).__chatStore = chatStore;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).__sessionStore = sessionStore;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).__testHelpers = {
        autoConfirm: false,
        confirmAll() {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (window as any).__testHelpers.autoConfirm = true;
        },
        confirmNone() {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (window as any).__testHelpers.autoConfirm = false;
        },
      };
    }

    // Fire all three in parallel — none depends on the others.
    const [fetched] = await Promise.all([
      promptStore.loadModes(),
      providerStore.loadProviders(),
      providerStore.loadAppInfo(),
    ]);
    if (fetched) modes = fetched;
  });

  // ---------------------------------------------------------------------------
  // Navigation guard — prevent leaving while streaming
  // ---------------------------------------------------------------------------

  beforeNavigate(({ cancel }) => {
    if (chatStore.isStreaming) {
      cancel();
    }
  });

  // ---------------------------------------------------------------------------
  // Navigation helpers — URL is source of truth
  // ---------------------------------------------------------------------------

  function navigateToNewChat() {
    if (chatStore.isStreaming) return;
    chatStore.resetForNewChat();
    const newId = crypto.randomUUID();
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- URL is source of truth
    goto(`/chat/${newId}`);
  }

  function navigateToSession(id: string) {
    if (id !== $page.params.id) {
      // eslint-disable-next-line svelte/no-navigation-without-resolve
      goto(`/chat/${id}`);
    }
  }

  async function handleFork(turnIndex: number) {
    const newId = await chatStore.forkSession(turnIndex);
    if (newId) {
      // eslint-disable-next-line svelte/no-navigation-without-resolve
      goto(`/chat/${newId}`);
    }
  }

  async function handleSaveTitle(newTitle: string) {
    try {
      await api.updateSessionTitle(currentSessionId, newTitle);
      await sessionStore.refresh();
    } catch (e) {
      console.error("Failed to update title:", e);
    }
  }

  // ---------------------------------------------------------------------------
  // Notes → Composer injection (called from ContextSidebar)
  // ---------------------------------------------------------------------------

  function insertNotesIntoComposer(notes: Note[]) {
    const block = chatStore.formatNotesForPrompt(notes);
    currentMessage = currentMessage.trim() ? `${currentMessage.trimEnd()}\n\n${block}` : block;

    requestAnimationFrame(() => {
      textareaEl?.focus();
      textareaEl?.setSelectionRange(currentMessage.length, currentMessage.length);
    });
  }
</script>

<svelte:head>
  <title>{providerStore.appTitle}</title>
</svelte:head>

<!--
  use:textSelection handles the full mouseup + click-away lifecycle.
  The onchatselect callback is the only wiring needed here.
-->
<div
  class="flex h-screen overflow-hidden bg-surface text-ink"
  use:textSelection={{ onchatselect: (hit) => (notePopup = hit) }}
>
  <!-- Global busy indicator for browser-based testing -->
  <div
    data-testid="app-busy"
    data-loading={editorStore.editState.status === "loading" ||
      chatStore.chatState.status === "loading"}
    data-busy-recent={busyRecent}
    data-page-ready={pageReady}
    class="hidden"
  ></div>

  <!-- ===================================================================== -->
  <!-- LEFT SIDEBAR — session list                                            -->
  <!-- ===================================================================== -->
  {#if sidebarResize.showLeft}
    <!-- Mobile backdrop -->
    <div
      data-testid="mobile-backdrop"
      class="fixed inset-0 z-20 bg-black/30 lg:hidden"
      onclick={() => sidebarResize.toggleLeft()}
      onkeydown={(e) => e.key === "Escape" && sidebarResize.toggleLeft()}
      role="button"
      tabindex="-1"
      aria-label="Close sidebar"
    ></div>
  {/if}

  <aside
    class="absolute inset-y-0 left-0 z-30 shrink-0 border-r border-line bg-panel p-2 shadow-lg transition-transform duration-200 lg:relative lg:shadow-[1px_0_0_rgba(38,35,31,0.03)] {sidebarResize.showLeft
      ? 'flex flex-col'
      : 'hidden -translate-x-full'}"
    style="width: {sidebarResize.leftWidth}px;"
  >
    <div class="mb-3">
      <p class="text-xs font-semibold tracking-[0.18em] text-muted uppercase">
        {providerStore.appTitle}
      </p>
      <h1 class="mt-1 text-xl font-semibold text-ink">Project conversations</h1>
    </div>

    <button
      onclick={navigateToNewChat}
      disabled={chatStore.isStreaming}
      class="mb-3 flex h-10 w-full items-center justify-center gap-2 rounded-md border border-line bg-[#131313] px-3 text-sm font-semibold text-ink shadow-sm transition hover:bg-ink focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span aria-hidden="true">+</span>
      New chat
    </button>

    <div class="scrollbar-hidden min-h-0 flex-1 overflow-y-auto">
      <SidebarLayout
        activeId={currentSessionId}
        onload={navigateToSession}
        isStreaming={chatStore.isStreaming}
      />
    </div>

    <!-- Left sidebar drag handle -->
    <button
      type="button"
      aria-label="Resize conversation sidebar"
      class="absolute top-0 -right-1 z-20 h-full w-2 cursor-col-resize touch-none transition hover:bg-accent/30 focus:bg-accent/30 focus:outline-none"
      onmousedown={sidebarResize.startLeftDrag}
      ondblclick={sidebarResize.resetLeft}
      onkeydown={(e) => kbResize.sidebar(e, "left")}
      title="Drag to resize. Double-click to reset."
    ></button>
  </aside>

  <!-- ===================================================================== -->
  <!-- MAIN AREA                                                              -->
  <!-- ===================================================================== -->
  <main class="flex min-w-0 flex-1 flex-col">
    {#if !pageReady}
      <!-- Loading skeleton -->
      <div class="flex flex-1 items-center justify-center">
        <div class="space-y-4 text-center">
          <div
            class="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent"
          ></div>
          <p class="text-sm text-muted">Loading session...</p>
        </div>
      </div>
    {:else}
      <ChatHeader
        sessionId={currentSessionId}
        title={sessionTitle}
        showLeft={sidebarResize.showLeft}
        ontoggleleft={() => sidebarResize.toggleLeft()}
        onsave={handleSaveTitle}
      />

      <!-- Chat scroll area -->
      <section
        class="scrollbar-hidden mx-auto min-h-0 w-full max-w-3xl flex-1 overflow-y-auto px-4 py-5 md:px-6"
      >
        <div class="flex flex-col gap-6">
          <!-- Fork status pill -->
          {#if chatStore.forkStatus}
            <p class="rounded-md border border-line bg-panel px-3 py-2 text-xs text-muted">
              {chatStore.forkStatus}
            </p>
          {/if}

          <ChatMessageList
            {systemPromptText}
            systemPromptIsOverride={hasSystemPromptOverride}
            systemPromptModeLabel={activeMode.label}
            systemPromptSaveState={editorStore.systemPromptState}
            systemPromptError={editorStore.systemPromptError}
            onsystemprompsave={(text) => editorStore.saveSystemPrompt(chatStore.sessionId, text)}
            onsystempromptreset={() => editorStore.clearSystemPrompt(chatStore.sessionId)}
            messages={chatStore.messages}
            isLoading={chatStore.chatState.status === "loading"}
            isBusy={editorStore.editState.status === "loading"}
            editingTurnId={editorStore.editingTurnId}
            editDraft={editorStore.editDraft}
            isSavingEdit={isEditSaving}
            editErrorMessage={editError ?? ""}
            onfork={handleFork}
            onedit={(turnId) => editorStore.startEditing(turnId, chatStore.messages)}
            ondelete={(turnId) => chatStore.deleteMessage(turnId, false)}
            onregenerate={() => chatStore.regenerateMessage()}
            oncopytext={(content) => navigator.clipboard.writeText(content)}
            oncopymarkdown={(content) => navigator.clipboard.writeText(content)}
            onsaveedit={() => chatStore.saveEdit()}
            oncanceledit={() => editorStore.cancelEditing()}
            ondraftchange={(text) => editorStore.setEditDraft(text)}
          />
        </div>
      </section>

      <ChatComposer
        providers={providerStore.providers}
        selectedModel={providerStore.selectedModel}
        onproviderchange={(p, m) => {
          providerStore.setProvider(p);
          providerStore.setModel(m);
        }}
        isStreaming={chatStore.isStreaming}
        onstop={() => chatStore.stopStreaming()}
        bind:currentMessage
        bind:textareaEl
      />
    {/if}
  </main>

  <!-- ===================================================================== -->
  <!-- RIGHT SIDEBAR — context injection + notes                             -->
  <!-- ===================================================================== -->
  {#if sidebarResize.showRight}
    <div
      class="relative hidden h-full shrink-0 lg:block"
      style="width: {sidebarResize.rightWidth}px;"
    >
      <!-- Right sidebar drag handle -->
      <button
        type="button"
        aria-label="Resize context sidebar"
        class="absolute top-0 -left-1 z-20 h-full w-2 cursor-col-resize touch-none transition hover:bg-accent/30 focus:bg-accent/30 focus:outline-none"
        onmousedown={sidebarResize.startRightDrag}
        ondblclick={sidebarResize.resetRight}
        onkeydown={(e) => kbResize.sidebar(e, "right")}
        title="Drag to resize. Double-click to reset."
      ></button>

      <ContextSidebar
        checkedFiles={chatStore.contextFiles}
        oncontextchange={(paths) => chatStore.setContextFiles(paths)}
        oninsertnotes={insertNotesIntoComposer}
        sessionId={currentSessionId}
      />
    </div>
  {/if}

  <!-- ===================================================================== -->
  <!-- FLOATING POPUP — Note (highlight inside a chat bubble)                -->
  <!-- ===================================================================== -->
  {#if notePopup}
    <NotePopup
      selectedText={notePopup.text}
      x={notePopup.x}
      y={notePopup.y}
      sessionId={currentSessionId}
      sourceRole={notePopup.sourceRole}
      ondismiss={() => (notePopup = null)}
    />
  {/if}
</div>

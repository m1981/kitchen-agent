<script lang="ts">
  /**
   * ChatMessageList
   * ================
   * Renders the scrollable list of chat messages (user + assistant bubbles)
   * including tool logs, image previews, and the "Thinking…" loading state.
   *
   * All per-message callbacks pass ``turn_id`` (the stable UUID stamped
   * at write time) instead of the array index.  This means the parent never
   * needs to track positions that shift when messages are deleted.
   *
   * Fires:
   *   onfork(turnIndex: number)      — user clicked the ⎇ Fork button
   *                                   (still index-based; fork uses position)
   *   onedit(turnId: string)         — user clicked ✏️ Edit
   *   ondelete(turnId: string)       — user clicked 🗑 Delete (single)
   *   ondeletepair(turnId: string)   — user clicked 🗑🗑 Delete with reply
   *
   * This component is purely presentational — it owns no async logic.
   */

  import type { Message, ToolLog } from "$lib/api";
  import Markdown from "./Markdown.svelte";
  import MessageEditor from "./MessageEditor.svelte";
  import MessageActions from "./MessageActions.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import SystemPromptBubble from "./SystemPromptBubble.svelte";
  import type { AsyncState } from "$lib/types";

  type Props = {
    // System prompt bubble
    systemPromptText: string;
    systemPromptIsOverride: boolean;
    systemPromptModeLabel: string;
    systemPromptSaveState: AsyncState<void>;
    systemPromptError: string;
    onsystemprompsave: (newText: string) => void;
    onsystempromptreset: () => void;
    // Messages
    messages: Message[];
    isLoading: boolean;
    isBusy: boolean;
    editingTurnId: string | null;
    editDraft: string;
    isSavingEdit: boolean;
    editErrorMessage: string;
    onfork: (turnIndex: number) => void;
    onedit: (turnId: string) => void;
    ondelete: (turnId: string) => void;
    onregenerate: () => void;
    oncopytext: (content: string) => void;
    oncopymarkdown: (content: string) => void;
    onsaveedit: () => void;
    oncanceledit: () => void;
    ondraftchange: (text: string) => void;
  };

  let {
    systemPromptText,
    systemPromptIsOverride,
    systemPromptModeLabel,
    systemPromptSaveState,
    systemPromptError,
    onsystemprompsave,
    onsystempromptreset,
    messages,
    isLoading,
    isBusy,
    editingTurnId,
    editDraft,
    isSavingEdit,
    editErrorMessage,
    onfork,
    onedit,
    ondelete,
    onregenerate,
    oncopytext,
    oncopymarkdown,
    onsaveedit,
    oncanceledit,
    ondraftchange,
  }: Props = $props();

  function formatToolResult(tool: ToolLog): string {
    return (tool.result.content as string | undefined) ?? JSON.stringify(tool.result, null, 2);
  }

  /**
   * Returns true if this is the last assistant message in the conversation.
   * Used to show the regenerate button.
   */
  function isLastAssistant(msgIndex: number): boolean {
    if (messages[msgIndex]?.role !== "assistant") return false;
    // Check if there are any messages after this one
    for (let i = msgIndex + 1; i < messages.length; i++) {
      if (messages[i].role === "assistant") return false;
    }
    return true;
  }

  /** Confirm before destructive delete */
  let confirmDeleteId = $state<string | null>(null);

  function requestDelete(turnId: string) {
    confirmDeleteId = turnId;
  }

  function doConfirmDelete() {
    if (confirmDeleteId) {
      ondelete(confirmDeleteId);
      confirmDeleteId = null;
    }
  }
</script>

<div class="space-y-3">
  <!-- System prompt bubble — always first -->
  <SystemPromptBubble
    text={systemPromptText}
    isOverride={systemPromptIsOverride}
    modeLabel={systemPromptModeLabel}
    saveState={systemPromptSaveState}
    errorMessage={systemPromptError}
    onsave={onsystemprompsave}
    onreset={onsystempromptreset}
  />

  {#each messages as msg, messageIndex (`${msg.role}-${msg.turn_id ?? messageIndex}`)}
    {@const isEditing = editingTurnId !== null && msg.turn_id === editingTurnId}

    <article
      data-testid="chat-bubble"
      data-chat-bubble={msg.role}
      data-turn-id={msg.turn_id}
      class="group/msg flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}"
      aria-label={msg.role === "user" ? "User message" : "Assistant message"}
    >
      <!-- Wrapper: card + actions stacked -->
      <div class="flex w-full flex-col gap-2 {msg.role === 'user' ? 'items-end' : ''}">
        <!-- Card -->
        <div
          class="flex w-full flex-col gap-2 rounded-xl {msg.role === 'user' ? 'p-4' : 'py-4'}"
          style={msg.role === "user" ? "background-color: #131313" : ""}
        >
          <!-- Badges (assistant only) -->
          {#if msg.role === "assistant"}
            <div class="flex items-center gap-2">
              {#if msg.token_count !== undefined && msg.token_count > 0}
                <span
                  title="Tokens used for this message"
                  class="hidden rounded-full border border-line bg-surface px-2 py-0.5 text-[10px] font-medium text-muted md:inline-block"
                >
                  {msg.token_count.toLocaleString()} tok
                </span>
              {/if}
              {#if msg.model}
                <span
                  title="{msg.provider || 'unknown'}/{msg.model}"
                  class="hidden rounded-full border border-line bg-surface px-2 py-0.5 text-[10px] font-medium text-muted md:inline-block"
                >
                  {msg.model}
                </span>
              {/if}
              {#if msg.tools && msg.tools.length > 0}
                <span
                  class="hidden rounded-full border border-line bg-surface px-2 py-0.5 text-xs font-medium text-muted md:inline-flex"
                >
                  {msg.tools.length} tools
                </span>
              {/if}
            </div>
          {/if}

          <!-- User image previews -->
          {#if msg.role === "user" && msg.images && msg.images.length > 0}
            <div class="flex flex-wrap gap-2">
              {#each msg.images as imgUrl, i (i)}
                <img
                  src={imgUrl}
                  alt="Attached image {i + 1}"
                  class="h-20 w-20 rounded border border-line object-cover"
                />
              {/each}
            </div>
          {/if}

          <!-- Context file badges — shown on user messages that had files injected -->
          {#if msg.role === "user" && msg.context_files && msg.context_files.length > 0}
            <div class="flex flex-wrap gap-1.5">
              {#each msg.context_files as filename (filename)}
                <span
                  title="Context file injected: {filename}"
                  class="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2 py-0.5 text-xs font-medium text-muted"
                >
                  📎 {filename}
                </span>
              {/each}
            </div>
          {/if}

          <!-- Message content or inline editor -->
          {#if isEditing}
            <MessageEditor
              draft={editDraft}
              isSaving={isSavingEdit}
              errorMessage={editErrorMessage}
              onsave={onsaveedit}
              oncancel={oncanceledit}
              {ondraftchange}
            />
          {:else}
            <Markdown content={msg.content} variant={msg.role} />
            {#if msg.isStreaming}
              <span class="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-accent"></span>
            {/if}
          {/if}

          <!-- Tool logs -->
          {#if msg.role === "assistant" && msg.tools && msg.tools.length > 0 && !isEditing}
            <div class="space-y-2 border-t border-line pt-3">
              <p class="text-xs font-semibold tracking-[0.14em] text-muted uppercase">Tools used</p>

              {#each msg.tools as tool, toolIndex (`${tool.name}-${toolIndex}`)}
                <details class="group rounded-md border border-line bg-surface">
                  <summary
                    class="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm"
                  >
                    <span class="min-w-0">
                      <span class="font-semibold text-ink">{tool.name}</span>
                      <span class="ml-2 text-xs text-muted">Args and result</span>
                      {#if (tool.token_count ?? Math.ceil(JSON.stringify(tool.result).length / 4)) > 0}
                        <span class="ml-1 text-[10px] text-muted/70"
                          >{tool.token_count !== undefined ? "" : "~"}{(
                            tool.token_count ?? Math.ceil(JSON.stringify(tool.result).length / 4)
                          ).toLocaleString()} tok</span
                        >
                      {/if}
                    </span>
                    <span class="text-xs font-medium text-accent group-open:hidden">View</span>
                    <span class="hidden text-xs font-medium text-accent group-open:inline"
                      >Hide</span
                    >
                  </summary>
                  <div class="space-y-3 border-t border-line px-3 py-3">
                    <div>
                      <p class="mb-1 text-xs font-semibold text-muted uppercase">Args</p>
                      <pre
                        class="overflow-x-auto rounded bg-code px-3 py-2 text-xs leading-5 text-code-ink">{JSON.stringify(
                          tool.args,
                          null,
                          2,
                        )}</pre>
                    </div>
                    <div>
                      <p class="mb-1 text-xs font-semibold text-muted uppercase">Result</p>
                      <pre
                        class="max-h-72 overflow-auto rounded bg-code px-3 py-2 text-xs leading-5 text-code-ink">{formatToolResult(
                          tool,
                        )}</pre>
                    </div>
                  </div>
                </details>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Action buttons (below card) -->
        {#if msg.turn_id}
          <MessageActions
            role={msg.role}
            turnId={msg.turn_id}
            content={msg.content}
            isLastAssistant={isLastAssistant(messageIndex)}
            {isBusy}
            {isEditing}
            onedit={() => onedit(msg.turn_id!)}
            ondelete={() => requestDelete(msg.turn_id!)}
            onfork={() => onfork(messageIndex)}
            {onregenerate}
            oncopytext={() => oncopytext?.(msg.content)}
            oncopymarkdown={() => oncopymarkdown?.(msg.content)}
          />
        {/if}
      </div>
    </article>
  {/each}

  {#if messages.length === 0 && !isLoading}
    <div class="flex flex-col items-center justify-center py-16 text-center">
      <div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10">
        <svg
          class="h-6 w-6 text-accent"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path
            d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
          />
        </svg>
      </div>
      <p class="text-sm font-medium text-ink">Start a conversation</p>
      <p class="mt-1 text-xs text-muted">Type a message below to begin</p>
    </div>
  {/if}

  {#if isLoading}
    <article data-testid="loading-indicator" class="flex justify-start">
      <div class="w-full rounded-xl py-4">
        <div class="flex items-center gap-3 text-sm text-muted">
          <span class="h-2 w-2 animate-pulse rounded-full bg-accent"></span>
          Thinking, reading files, and preparing the answer…
        </div>
      </div>
    </article>
  {/if}
</div>

{#if confirmDeleteId}
  <ConfirmDialog
    message="Delete this message from the conversation history?"
    onconfirm={doConfirmDelete}
    oncancel={() => (confirmDeleteId = null)}
  />
{/if}

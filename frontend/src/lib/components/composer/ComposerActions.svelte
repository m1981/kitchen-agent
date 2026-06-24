<script lang="ts">
  /**
   * ComposerActions
   * ===============
   * Action buttons for the chat composer:
   *   - Left: Tools toggle
   *   - Center: Model selector
   *   - Right: Send/Stop
   */
  import { promptStore } from "$lib/stores/prompt.svelte";
  import type { ProviderInfo } from "$lib/providers";
  import ModelSelector from "./ModelSelector.svelte";

  type Props = {
    providers: ProviderInfo[];
    selectedModel: string;
    onproviderchange: (provider: string, model: string) => void;
    isStreaming: boolean;
    onstop?: () => void;
    onsend: () => void;
    canSend: boolean;
  };

  let { providers, selectedModel, onproviderchange, isStreaming, onstop, onsend, canSend }: Props =
    $props();
</script>

<div class="buttons-row">
  <!-- Left: tools toggle -->
  <div class="buttons-left">
    <button
      type="button"
      data-testid="tools-toggle"
      class="tools-btn"
      class:tools-active={promptStore.toolsEnabled}
      onclick={() => promptStore.toggleTools()}
      aria-pressed={promptStore.toolsEnabled}
      title={promptStore.toolsEnabled
        ? "Tools ON — LLM can read and edit your knowledge base"
        : "Tools OFF — Direct LLM reply, no file access"}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
      <span>Tools</span>
    </button>
  </div>

  <!-- Center: model selector -->
  <div class="buttons-center">
    <ModelSelector {providers} {selectedModel} {onproviderchange} />
  </div>

  <!-- Right: send/stop -->
  <div class="buttons-right">
    {#if isStreaming}
      <button
        onclick={() => onstop?.()}
        data-testid="stop-btn"
        class="stop-btn"
        title="Stop generation"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      </button>
    {:else}
      <button
        onclick={onsend}
        disabled={!canSend}
        data-testid="send-btn"
        class="send-btn"
        title="Send (⌘↵)"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    {/if}
  </div>
</div>

<style>
  /* ── Buttons row ──────────────────────────────────────────────────── */

  .buttons-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    gap: 8px;
  }

  .buttons-left,
  .buttons-right {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .buttons-center {
    flex: 1;
    display: flex;
    justify-content: center;
  }

  /* ── Tools button ─────────────────────────────────────────────────── */

  .tools-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 32px;
    padding: 0 12px;
    border-radius: 8px;
    border: 1px solid #363635;
    background: #131313;
    color: #c3c3c2;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .tools-btn:hover {
    background: #1f1f1f;
    border-color: #4a4a49;
  }

  .tools-btn.tools-active {
    background: #2d1a17;
    border-color: #be5637;
    color: #be5637;
  }

  .tools-btn.tools-active:hover {
    background: #3d241f;
  }

  /* ── Send / Stop button (icon only, circular) ─────────────────────── */

  .send-btn,
  .stop-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    padding: 0;
    border-radius: 50%;
    border: none;
    background: #be5637;
    color: #fff;
    cursor: pointer;
    transition:
      background 0.15s,
      box-shadow 0.15s,
      opacity 0.15s;
  }

  .send-btn:hover:not(:disabled) {
    background: #a44a2f;
    box-shadow: 0 1px 3px rgba(190, 86, 55, 0.4);
  }

  .send-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .stop-btn {
    background: #ea4335;
  }

  .stop-btn:hover {
    background: #c5221f;
    box-shadow: 0 1px 3px rgba(234, 67, 53, 0.4);
  }
</style>

<script lang="ts">
  /**
   * ModelSelector
   * =============
   * Compact dropdown for picking an LLM model grouped by provider.
   * Inspired by Anthropic's minimal design language.
   *
   * Props:
   *   providers         — list of provider metadata from the API
   *   selectedModel     — currently selected model ID
   *   onproviderchange  — called with (providerId, modelId) on change
   */
  import type { ProviderInfo } from "$lib/providers";

  type Props = {
    providers: ProviderInfo[];
    selectedModel: string;
    onproviderchange: (provider: string, model: string) => void;
  };

  let { providers, selectedModel, onproviderchange }: Props = $props();

  type FlatModel = {
    id: string;
    label: string;
    providerId: string;
    providerLabel: string;
    context_k: number;
  };

  const allModels: FlatModel[] = $derived(
    providers.flatMap((p) =>
      p.models.map((m) => ({
        id: m.id,
        label: m.label,
        providerId: p.id,
        providerLabel: p.label,
        context_k: m.context_k,
      })),
    ),
  );

  type ModelGroup = {
    providerId: string;
    providerLabel: string;
    models: { id: string; label: string; context_k: number }[];
  };

  const modelGroups: ModelGroup[] = $derived(
    providers.map((p) => ({
      providerId: p.id,
      providerLabel: p.label,
      models: p.models.map((m) => ({ id: m.id, label: m.label, context_k: m.context_k })),
    })),
  );

  const currentModel = $derived(allModels.find((m) => m.id === selectedModel) ?? allModels[0]);

  let isOpen = $state(false);
  let dropdownEl = $state<HTMLDivElement | null>(null);

  function selectModel(model: FlatModel) {
    onproviderchange(model.providerId, model.id);
    isOpen = false;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      isOpen = false;
    }
  }

  function handleClickOutside(e: MouseEvent) {
    if (dropdownEl && !dropdownEl.contains(e.target as Node)) {
      isOpen = false;
    }
  }

  /** Format context window size for display */
  function formatContext(contextK: number): string {
    if (contextK >= 1000) {
      return (contextK / 1000).toFixed(0) + "M";
    }
    return contextK + "K";
  }
</script>

<svelte:window onclick={handleClickOutside} onkeydown={handleKeydown} />

{#if allModels.length > 0}
  <div class="model-selector" bind:this={dropdownEl}>
    <!-- Trigger button -->
    <button
      type="button"
      class="model-trigger"
      onclick={() => (isOpen = !isOpen)}
      aria-haspopup="listbox"
      aria-expanded={isOpen}
      aria-label="Select model"
    >
      <span class="model-name">{currentModel?.label ?? "Select"}</span>
      <svg
        class="chevron"
        class:rotate-180={isOpen}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <!-- Desktop dropdown -->
    {#if isOpen}
      <div class="dropdown" role="listbox" aria-label="Available models">
        {#each modelGroups as group, groupIdx (group.providerId)}
          {#if groupIdx > 0}
            <div class="separator"></div>
          {/if}
          {#if modelGroups.length > 1}
            <div class="group-label">{group.providerLabel}</div>
          {/if}
          <div class="group" role="group">
            {#each group.models as model (model.id)}
              <button
                type="button"
                class="menu-item"
                class:selected={model.id === currentModel?.id}
                onclick={() =>
                  selectModel({
                    id: model.id,
                    label: model.label,
                    providerId: group.providerId,
                    providerLabel: group.providerLabel,
                    context_k: model.context_k,
                  })}
                role="option"
                aria-selected={model.id === currentModel?.id}
              >
                <span class="item-label">{model.label}</span>
                <span class="item-meta">{formatContext(model.context_k)}</span>
              </button>
            {/each}
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<!-- Mobile bottom sheet -->
{#if isOpen}
  <div class="mobile-overlay" role="dialog" aria-label="Select model">
    <div
      class="mobile-backdrop"
      onclick={() => (isOpen = false)}
      onkeydown={(e) => e.key === "Escape" && (isOpen = false)}
      role="button"
      tabindex="-1"
    ></div>
    <div class="mobile-sheet">
      <div class="mobile-header">
        <span class="mobile-title">Model</span>
        <button type="button" class="mobile-close" onclick={() => (isOpen = false)}>
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="mobile-body">
        {#each modelGroups as group, groupIdx (group.providerId)}
          {#if groupIdx > 0}
            <div class="mobile-separator"></div>
          {/if}
          {#if modelGroups.length > 1}
            <div class="mobile-group-label">{group.providerLabel}</div>
          {/if}
          {#each group.models as model (model.id)}
            <button
              type="button"
              class="mobile-item"
              class:selected={model.id === currentModel?.id}
              onclick={() =>
                selectModel({
                  id: model.id,
                  label: model.label,
                  providerId: group.providerId,
                  providerLabel: group.providerLabel,
                  context_k: model.context_k,
                })}
            >
              <span class="mobile-item-label">{model.label}</span>
              <span class="mobile-item-meta">{formatContext(model.context_k)}</span>
              {#if model.id === currentModel?.id}
                <svg
                  class="mobile-check"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              {/if}
            </button>
          {/each}
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  /* ── Trigger ──────────────────────────────────────────────────────── */

  .model-selector {
    position: relative;
  }

  .model-trigger {
    display: flex;
    align-items: center;
    gap: 4px;
    height: 32px;
    padding: 0 8px;
    border-radius: 6px;
    border: 1px solid #363635;
    background: #131313;
    color: #c3c3c2;
    font-family: inherit;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    max-width: 160px;
  }

  .model-trigger:hover {
    background: #1f1f1f;
    border-color: #4a4a49;
  }

  .model-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chevron {
    width: 12px;
    height: 12px;
    flex-shrink: 0;
    transition: transform 0.15s;
    color: #8a8a88;
  }

  /* ── Desktop dropdown (compact) ───────────────────────────────────── */

  .dropdown {
    position: absolute;
    bottom: 100%;
    left: 0;
    min-width: 200px;
    max-height: 320px;
    overflow-y: auto;
    background: #272726;
    border: 1px solid #363635;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 50;
    margin-bottom: 4px;
    padding: 4px;
  }

  .separator {
    height: 1px;
    background: #363635;
    margin: 4px 0;
  }

  .group-label {
    padding: 6px 8px 2px;
    font-family: inherit;
    font-size: 12px;
    font-weight: 500;
    color: #8a8a88;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .group {
    padding: 0;
  }

  .menu-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 6px 8px;
    border: none;
    background: transparent;
    text-align: left;
    cursor: pointer;
    border-radius: 4px;
    transition: background 0.1s;
    font-family: inherit;
    gap: 8px;
    color: #c3c3c2;
  }

  .menu-item:hover {
    background: #363635;
  }

  .menu-item.selected {
    background: #2d1a17;
  }

  .item-label {
    font-size: 14px;
    color: #111827;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  .item-meta {
    font-size: 12px;
    color: #8a8a88;
    white-space: nowrap;
    flex-shrink: 0;
  }

  /* ── Mobile bottom sheet (compact) ────────────────────────────────── */

  .mobile-overlay {
    display: none;
  }

  @media (max-width: 1023px) {
    .dropdown {
      display: none;
    }

    .mobile-overlay {
      display: block;
      position: fixed;
      inset: 0;
      z-index: 100;
    }

    .mobile-backdrop {
      position: absolute;
      inset: 0;
      background: rgba(0, 0, 0, 0.4);
    }

    .mobile-sheet {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: #272726;
      border-radius: 12px 12px 0 0;
      max-height: 60vh;
      display: flex;
      flex-direction: column;
      animation: slide-up 0.2s ease-out;
    }

    @keyframes slide-up {
      from {
        transform: translateY(100%);
      }
      to {
        transform: translateY(0);
      }
    }

    .mobile-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      border-bottom: 1px solid #363635;
    }

    .mobile-title {
      font-family: inherit;
      font-size: 14px;
      font-weight: 600;
      color: #c3c3c2;
    }

    .mobile-close {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      border: none;
      background: #363635;
      border-radius: 50%;
      color: #8a8a88;
      cursor: pointer;
    }

    .mobile-body {
      overflow-y: auto;
      padding: 4px;
    }

    .mobile-separator {
      height: 1px;
      background: #363635;
      margin: 4px 0;
    }

    .mobile-group-label {
      padding: 8px 12px 4px;
      font-family: inherit;
      font-size: 12px;
      font-weight: 500;
      color: #8a8a88;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .mobile-item {
      display: flex;
      align-items: center;
      width: 100%;
      padding: 10px 12px;
      min-height: 44px;
      border: none;
      background: transparent;
      text-align: left;
      cursor: pointer;
      border-radius: 6px;
      transition: background 0.1s;
      font-family: inherit;
      gap: 8px;
      color: #c3c3c2;
    }

    .mobile-item:hover {
      background: #363635;
    }

    .mobile-item.selected {
      background: #2d1a17;
    }

    .mobile-item-label {
      font-size: 14px;
      color: #c3c3c2;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
      min-width: 0;
    }

    .mobile-item-meta {
      font-size: 12px;
      color: #8a8a88;
      white-space: nowrap;
      flex-shrink: 0;
    }

    .mobile-check {
      color: #be5637;
      flex-shrink: 0;
    }
  }
</style>

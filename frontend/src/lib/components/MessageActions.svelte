<script lang="ts">
  /**
   * MessageActions
   * ===============
   * Action bar for chat messages, inspired by Google AI Studio.
   *
   * Layout:
   *   - Primary actions inline: Edit, Regenerate
   *   - Secondary actions in dropdown: Delete, Fork, Copy
   */

  import { smartPosition } from "$lib/actions/smartPosition";

  type Props = {
    role: "user" | "assistant";
    turnId: string | null | undefined;
    content?: string;
    isLastAssistant?: boolean;
    isBusy?: boolean;
    isEditing?: boolean;
    onedit?: () => void;
    ondelete?: () => void;
    onfork?: () => void;
    onregenerate?: () => void;
    oncopytext?: () => void;
    oncopymarkdown?: () => void;
  };

  let {
    role,
    turnId,
    content = "",
    isLastAssistant = false,
    isBusy = false,
    isEditing = false,
    onedit,
    ondelete,
    onfork,
    onregenerate,
    oncopytext,
    oncopymarkdown,
  }: Props = $props();

  let copied = $state(false);

  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(content);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch (e) {
      console.error("Copy failed:", e);
    }
  }

  let menuOpen = $state(false);
  let menuRef = $state<HTMLDivElement | null>(null);
  let triggerEl = $state<HTMLButtonElement | null>(null);

  function toggleMenu() {
    menuOpen = !menuOpen;
  }

  function closeMenu() {
    menuOpen = false;
  }

  function handleMenuAction(action: () => void) {
    action();
    closeMenu();
  }

  // Close menu on click outside
  function handleClickOutside(e: MouseEvent) {
    if (menuRef && !menuRef.contains(e.target as Node)) {
      closeMenu();
    }
  }

  // Close menu on escape
  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") closeMenu();
  }
</script>

<svelte:window on:click={handleClickOutside} on:keydown={handleKeydown} />

{#if turnId}
  <div
    class="flex items-center gap-0.5 opacity-0 transition-opacity group-hover/msg:opacity-100 focus-within:opacity-100 {role ===
    'assistant'
      ? 'justify-end'
      : ''}"
    aria-label="Message actions"
  >
    <!-- Copy button (primary) -->
    <button
      onclick={copyToClipboard}
      data-testid="copy-btn"
      title={copied ? "Copied!" : "Copy message"}
      aria-label="Copy message"
      class="action-btn {role === 'user' ? 'action-btn-user' : 'action-btn-assistant'}"
    >
      {#if copied}
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      {:else}
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      {/if}
    </button>

    <!-- Edit button (primary) -->
    {#if !isEditing && onedit}
      <button
        onclick={onedit}
        disabled={isBusy}
        data-testid="edit-btn"
        title="Edit message"
        aria-label="Edit message"
        class="action-btn {role === 'user' ? 'action-btn-user' : 'action-btn-assistant'}"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
      </button>
    {/if}

    <!-- Regenerate button (primary, last assistant only) -->
    {#if isLastAssistant && onregenerate}
      <button
        onclick={onregenerate}
        disabled={isBusy}
        data-testid="regenerate-btn"
        title="Regenerate response"
        aria-label="Regenerate response"
        class="action-btn action-btn-assistant"
      >
        <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
          <path
            d="M10 17.5833C10 16.5278 9.79861 15.5417 9.39583 14.625C9.00694 13.7083 8.46528 12.9097 7.77083 12.2292C7.09028 11.5347 6.29167 10.9931 5.375 10.6042C4.45833 10.2014 3.47222 10 2.41667 10C3.47222 10 4.45833 9.80556 5.375 9.41667C6.29167 9.01389 7.09028 8.47222 7.77083 7.79167C8.46528 7.09722 9.00694 6.29167 9.39583 5.375C9.79861 4.44444 10 3.45833 10 2.41667C10 3.45833 10.1944 4.44444 10.5833 5.375C10.9861 6.29167 11.5278 7.09722 12.2083 7.79167C12.9028 8.47222 13.7083 9.01389 14.625 9.41667C15.5556 9.80556 16.5417 10 17.5833 10C16.5417 10 15.5556 10.2014 14.625 10.6042C13.7083 10.9931 12.9028 11.5347 12.2083 12.2292C11.5278 12.9097 10.9861 13.7083 10.5833 14.625C10.1944 15.5417 10 16.5278 10 17.5833Z"
            fill="url(#regenerate-gradient)"
          />
          <defs>
            <linearGradient
              id="regenerate-gradient"
              x1="10"
              y1="0"
              x2="10"
              y2="20"
              gradientUnits="userSpaceOnUse"
            >
              <stop stop-color="#87A9FF" />
              <stop offset="0.44" stop-color="#A7B8EE" />
              <stop offset="0.88" stop-color="#F1DCC7" />
            </linearGradient>
          </defs>
        </svg>
      </button>
    {/if}

    <!-- More options button (secondary actions dropdown) -->
    <div class="relative" bind:this={menuRef}>
      <button
        bind:this={triggerEl}
        onclick={toggleMenu}
        disabled={isBusy}
        data-testid="more-options-btn"
        title="More options"
        aria-label="More options"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        class="action-btn {role === 'user' ? 'action-btn-user' : 'action-btn-assistant'}"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="5" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="12" cy="19" r="2" />
        </svg>
      </button>

      <!-- Dropdown menu -->
      {#if menuOpen}
        <div
          use:smartPosition={{ trigger: triggerEl!, placement: "bottom-end" }}
          class="dropdown-menu"
          role="menu"
        >
          {#if oncopytext}
            <button
              onclick={() => handleMenuAction(oncopytext!)}
              class="menu-item"
              role="menuitem"
              data-testid="copy-text-btn"
            >
              <svg
                class="menu-icon"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <span>Copy as text</span>
            </button>
          {/if}

          {#if oncopymarkdown}
            <button
              onclick={() => handleMenuAction(oncopymarkdown!)}
              class="menu-item"
              role="menuitem"
              data-testid="copy-markdown-btn"
            >
              <svg
                class="menu-icon"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
              <span>Copy as markdown</span>
            </button>
          {/if}

          {#if onfork}
            <button
              onclick={() => handleMenuAction(onfork!)}
              class="menu-item"
              role="menuitem"
              data-testid="fork-btn"
            >
              <svg
                class="menu-icon"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <circle cx="18" cy="18" r="3" />
                <circle cx="6" cy="6" r="3" />
                <path d="M13 6h3a2 2 0 0 1 2 2v7" />
                <line x1="6" y1="9" x2="6" y2="21" />
              </svg>
              <span>Branch from here</span>
            </button>
          {/if}

          {#if ondelete}
            <div class="menu-divider"></div>
            <button
              onclick={() => handleMenuAction(ondelete!)}
              class="menu-item menu-item-danger"
              role="menuitem"
              data-testid="delete-btn"
            >
              <svg
                class="menu-icon"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="3 6 5 6 21 6" />
                <path
                  d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                />
              </svg>
              <span>Delete</span>
            </button>
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 6px;
    transition: all 0.15s ease;
  }

  .action-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .action-btn-user {
    color: rgba(255, 255, 255, 0.6);
  }

  .action-btn-user:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    color: white;
  }

  .action-btn-assistant {
    color: var(--color-muted, #6b7280);
  }

  .action-btn-assistant:hover:not(:disabled) {
    background: var(--color-line, #e5e7eb);
    color: var(--color-ink, #111827);
  }

  /* ── Dropdown menu: always dark text on white bg ── */

  .dropdown-menu {
    position: fixed;
    z-index: 50;
    margin-top: 4px;
    min-width: 180px;
    border-radius: 8px;
    border: 1px solid #363635;
    background: #272726;
    padding: 4px 0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    color: #c3c3c2;
  }

  .menu-divider {
    margin: 4px 0;
    border-top: 1px solid #e5e7eb;
  }

  .menu-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 8px 12px;
    font-size: 12px;
    text-align: left;
    color: #c3c3c2;
    background: transparent;
    border: none;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .menu-item :global(.menu-icon) {
    color: #6b7280;
    flex-shrink: 0;
  }

  .menu-item:hover {
    background: #363635;
  }

  .menu-item-danger {
    color: #ef4444;
  }

  .menu-item-danger :global(.menu-icon) {
    color: #dc2626;
  }

  .menu-item-danger:hover {
    background: #2d1a1a;
  }
</style>

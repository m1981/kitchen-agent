<script lang="ts">
  /**
   * SessionTreeNode
   * ================
   * Renders one node in the session tree and, recursively, its children.
   * Self-imports for recursion, as required by Svelte 5.
   *
   * Visual behaviour:
   *   - Active session → accent left-border highlight.
   *   - Archived node  → dimmed + italic title.
   *   - Fork indicator → small ⎇ badge with fork_turn_index.
   *   - Children       → indented below with a subtle tree line.
   *   - ⋯ context menu → export md / export llm json / archive / restore / delete.
   */
  import SessionContextMenu from "./SessionContextMenu.svelte";
  import SessionTreeNode from "./SessionTreeNode.svelte";
  import type { SessionNode } from "$lib/api";

  type Props = {
    node: SessionNode;
    depth?: number;
    activeId: string | null;
    onload: (id: string) => void;
    onarchive: (id: string) => void;
    onunarchive: (id: string) => void;
    ondelete: (id: string) => void;
    onexport: (id: string) => Promise<void>;
    onexportllm: (id: string) => Promise<void>;
    ontitlegenerate?: (id: string) => Promise<void>;
  };

  let {
    node,
    depth = 0,
    activeId,
    onload,
    onarchive,
    onunarchive,
    ondelete,
    onexport,
    onexportllm,
    ontitlegenerate,
  }: Props = $props();

  let expanded = $state(false);

  function countDescendants(node: SessionNode): number {
    return node.children.reduce((total, child) => total + 1 + countDescendants(child), 0);
  }

  function containsSession(node: SessionNode, id: string | null): boolean {
    if (id === null) return false;
    if (node.id === id) return true;
    return node.children.some((child) => containsSession(child, id));
  }

  const isActive = $derived(node.id === activeId);
  const isArchived = $derived(node.archived_at !== null);
  const hasChildren = $derived(node.children.length > 0);
  const isForked = $derived(node.parent_id !== null);
  const displayTitle = $derived(node.title ?? node.id.slice(0, 8));
  const branchCount = $derived(countDescendants(node));
  const activeInBranch = $derived(containsSession(node, activeId));

  $effect(() => {
    if (activeInBranch && hasChildren) expanded = true;
  });
</script>

<div>
  <!-- ── This node ─────────────────────────────────────────────────────── -->
  <div
    class="group flex items-center gap-1 rounded-md px-2 py-1 transition
	       {isActive
      ? 'bg-accent-soft shadow-[inset_3px_0_0_var(--color-accent)]'
      : hasChildren && depth === 0
        ? 'bg-surface/60 hover:bg-surface'
        : 'hover:bg-surface'}
	       {isArchived ? 'opacity-40' : ''}"
    style="padding-left: {4 + depth * 10}px"
  >
    <!-- Expand / collapse caret (only when children exist) -->
    {#if hasChildren}
      <button
        onclick={() => (expanded = !expanded)}
        class="flex h-4 w-4 shrink-0 items-center justify-center rounded text-muted
			       hover:text-ink focus:outline-none"
        aria-label={expanded ? "Collapse branch group" : "Expand branch group"}
        aria-expanded={expanded}
        title={expanded ? "Collapse branch group" : "Expand branch group"}
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="currentColor"
          class="transition-transform {expanded ? 'rotate-90' : ''}"
          aria-hidden="true"
        >
          <path d="M3 2 L7 5 L3 8 Z" />
        </svg>
      </button>
    {:else}
      <!-- Leaf spacer (aligns with caret) -->
      <span class="h-4 w-4 shrink-0" aria-hidden="true"></span>
    {/if}

    <!-- Title button -->
    <button
      onclick={() => onload(node.id)}
      class="min-w-0 flex-1 truncate text-left text-sm
			       {isActive ? 'font-semibold text-ink' : 'font-medium text-muted hover:text-ink'}
			       {isArchived ? 'italic' : ''}"
      title={displayTitle}
    >
      {displayTitle}
    </button>

    <!-- Fork badge -->
    {#if isForked && node.fork_turn_index !== null}
      <span
        class="shrink-0 rounded-full border border-line bg-surface px-1.5 py-0 text-[10px]
				       font-medium text-muted"
        title="Forked at turn {node.fork_turn_index}"
        aria-label="Forked at turn {node.fork_turn_index}"
      >
        ⎇{node.fork_turn_index}
      </span>
    {/if}

    {#if hasChildren}
      <span
        class="shrink-0 rounded-full border border-line bg-panel px-1.5 py-0 text-[10px]
				       font-medium text-muted"
        title="{branchCount} branched chat{branchCount === 1 ? '' : 's'}"
        aria-label="{branchCount} branched chat{branchCount === 1 ? '' : 's'}"
      >
        {branchCount}
      </span>
    {/if}

    <!-- Context menu -->
    <SessionContextMenu
      {node}
      {onarchive}
      {onunarchive}
      {ondelete}
      {onexport}
      {onexportllm}
      {ontitlegenerate}
    />
  </div>

  <!-- ── Children ──────────────────────────────────────────────────────── -->
  {#if expanded && hasChildren}
    <div class="relative">
      <!-- Subtle vertical tree line -->
      <div
        class="absolute top-0 bottom-0 w-px bg-line"
        style="left: {depth * 10 + 8}px"
        aria-hidden="true"
      ></div>

      {#each node.children as child (child.id)}
        <SessionTreeNode
          node={child}
          depth={depth + 1}
          {activeId}
          {onload}
          {onarchive}
          {onunarchive}
          {ondelete}
          {onexport}
          {onexportllm}
          {ontitlegenerate}
        />
      {/each}
    </div>
  {/if}
</div>

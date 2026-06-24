/**
 * src/lib/stores/sessions.svelte.ts
 * ==================================
 * Rune-based store for the session tree.
 *
 * Owns:
 *   - the tree fetched from GET /api/sessions/tree
 *   - the currently active session ID
 *   - archive / unarchive / delete operations (with optimistic removal)
 *
 * Consumers should call `sessionStore.refresh()` on mount and after any
 * mutation that changes the tree shape (fork, new chat, delete).
 */

import { api, type SessionNode } from "$lib/api";
import type { AsyncState } from "$lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Flatten a forest into a plain array for O(1) ID lookups. */
function flatten(nodes: SessionNode[]): SessionNode[] {
  const result: SessionNode[] = [];
  function walk(ns: SessionNode[]) {
    for (const n of ns) {
      result.push(n);
      walk(n.children);
    }
  }
  walk(nodes);
  return result;
}

function normalizeTree(value: unknown): SessionNode[] {
  if (!Array.isArray(value)) {
    throw new Error("Invalid session tree response.");
  }
  return value.map(normalizeNode);
}

function normalizeNode(node: SessionNode): SessionNode {
  return {
    ...node,
    children: Array.isArray(node.children) ? node.children.map(normalizeNode) : [],
  };
}

/** Remove a node by ID anywhere in the tree (used for optimistic delete). */
function removeById(nodes: SessionNode[], id: string): SessionNode[] {
  return nodes
    .filter((n) => n.id !== id)
    .map((n) => ({ ...n, children: removeById(n.children, id) }));
}

/** Stamp archived_at on a node anywhere in the tree (optimistic archive). */
function stampArchived(nodes: SessionNode[], id: string, stamp: string | null): SessionNode[] {
  return nodes.map((n) => {
    if (n.id === id) return { ...n, archived_at: stamp };
    return { ...n, children: stampArchived(n.children, id, stamp) };
  });
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createSessionStore() {
  let tree = $state<SessionNode[]>([]);
  let fetchState = $state<AsyncState<SessionNode[]>>({ status: "idle" });
  let activeId = $state<string | null>(null);

  // Derived flat list — recomputed whenever `tree` mutates.
  const flat = $derived(flatten(tree));

  return {
    // ── Reads ────────────────────────────────────────────────────────────
    get tree() {
      return tree;
    },
    /** Flat list of every node — useful for title lookups by ID. */
    get flat() {
      return flat;
    },
    get fetchState() {
      return fetchState;
    },
    get activeId() {
      return activeId;
    },

    /**
     * Get the title for a specific session by ID.
     * Returns null if session not found or has no title.
     */
    getTitleById(id: string): string | null {
      const node = flat.find((n) => n.id === id);
      return node?.title ?? null;
    },

    // ── Mutations ────────────────────────────────────────────────────────

    setActive(id: string) {
      activeId = id;
    },

    async refresh() {
      fetchState = { status: "loading" };
      try {
        tree = normalizeTree(await api.getSessionTree());
        fetchState = { status: "success", data: tree };
      } catch (e) {
        fetchState = { status: "error", message: String(e) };
      }
    },

    async archive(id: string) {
      // Optimistic: stamp immediately so the UI greys it out at once.
      tree = stampArchived(tree, id, new Date().toISOString());
      try {
        await api.archiveSession(id);
      } catch (e) {
        // Rollback: clear the stamp.
        tree = stampArchived(tree, id, null);
        throw e;
      }
    },

    async unarchive(id: string) {
      // Optimistic: clear stamp immediately.
      tree = stampArchived(tree, id, null);
      try {
        await api.unarchiveSession(id);
      } catch (e) {
        // Rollback: re-stamp (we don't know the original value so re-fetch).
        await this.refresh();
        throw e;
      }
    },

    async delete(id: string) {
      // Optimistic removal — but only from the local tree snapshot.
      const previous = tree;
      tree = removeById(tree, id);
      try {
        await api.deleteSession(id);
        // If the deleted session was active, clear it.
        if (activeId === id) activeId = null;
      } catch (e) {
        tree = previous; // rollback
        throw e;
      }
    },

    // ── Tree Operations ─────────────────────────────────────────────────

    /**
     * Get session state flags for UI decisions.
     */
    async getSessionFlags(id: string) {
      return api.getSessionFlags(id);
    },

    /**
     * Archive session and optionally all children.
     */
    async archiveTree(id: string, includeChildren: boolean = false) {
      // Optimistic: stamp all affected sessions
      const idsToArchive = [id];
      if (includeChildren) {
        // Get children from tree
        const node = flat.find((n) => n.id === id);
        if (node) {
          function collectChildren(n: typeof node): string[] {
            const ids: string[] = [];
            for (const child of n.children) {
              ids.push(child.id);
              ids.push(...collectChildren(child));
            }
            return ids;
          }
          idsToArchive.push(...collectChildren(node));
        }
      }

      // Optimistic stamp
      const now = new Date().toISOString();
      for (const archiveId of idsToArchive) {
        tree = stampArchived(tree, archiveId, now);
      }

      try {
        await api.archiveSessionTree(id, includeChildren);
      } catch (e) {
        // Rollback
        for (const archiveId of idsToArchive) {
          tree = stampArchived(tree, archiveId, null);
        }
        throw e;
      }
    },

    /**
     * Unarchive session and optionally all children.
     */
    async unarchiveTree(id: string, includeChildren: boolean = false) {
      // Optimistic: clear stamp for all affected sessions
      const idsToUnarchive = [id];
      if (includeChildren) {
        const node = flat.find((n) => n.id === id);
        if (node) {
          function collectChildren(n: typeof node): string[] {
            const ids: string[] = [];
            for (const child of n.children) {
              ids.push(child.id);
              ids.push(...collectChildren(child));
            }
            return ids;
          }
          idsToUnarchive.push(...collectChildren(node));
        }
      }

      // Optimistic clear
      for (const unarchiveId of idsToUnarchive) {
        tree = stampArchived(tree, unarchiveId, null);
      }

      try {
        await api.unarchiveSessionTree(id, includeChildren);
      } catch (e) {
        // Rollback: re-fetch
        await this.refresh();
        throw e;
      }
    },

    /**
     * Check if session has children (is fork parent).
     */
    hasChildren(id: string): boolean {
      const node = flat.find((n) => n.id === id);
      return node ? node.children.length > 0 : false;
    },

    /**
     * Get children count for a session.
     */
    getChildrenCount(id: string): number {
      const node = flat.find((n) => n.id === id);
      return node ? node.children.length : 0;
    },
  };
}

// Singleton — one instance for the whole app.
export const sessionStore = createSessionStore();

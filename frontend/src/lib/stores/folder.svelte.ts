/**
 * src/lib/stores/folder.svelte.ts
 * ================================
 * Class-based rune store for folder organization.
 *
 * Owns:
 *   - the folder list fetched from GET /api/folders
 *   - session cache per folder (moved from FolderItem)
 *   - expanded state per folder (moved from FolderTree)
 *   - drag and drop state for session-to-folder assignment
 *   - CRUD operations with optimistic updates
 *
 * Design decisions:
 *   - Class-based (not closure-based) for reliable $state reactivity
 *   - Session cache co-located here to fix drag-drop refresh bug
 *   - expandedFolders uses SvelteSet for reactive .has()
 */

import { api, type Folder, type FolderCreateRequest, type FolderUpdateRequest } from "$lib/api";
import type { AsyncState, DragPayload, DropTarget, FolderSession } from "$lib/types";
import { SvelteMap, SvelteSet } from "svelte/reactivity";

// ---------------------------------------------------------------------------
// Store class
// ---------------------------------------------------------------------------

class FolderStore {
  // ── Folder CRUD state ──────────────────────────────────────────────────
  folders = $state<Folder[]>([]);
  fetchState = $state<AsyncState<Folder[]>>({ status: "idle" });

  // ── Session cache (moved from FolderItem) ──────────────────────────────
  // SvelteMap/SvelteSet have built-in reactivity — do NOT wrap in $state.
  // Wrapping in $state creates a deep proxy that intercepts .set()/.delete()
  // calls and breaks SvelteMap's internal notification mechanism.
  folderSessions = new SvelteMap<string, FolderSession[]>();
  sessionsLoading = new SvelteMap<string, boolean>();
  sessionsError = new SvelteMap<string, string | null>();

  // ── Expanded state (moved from FolderTree) ─────────────────────────────
  expandedFolders = new SvelteSet<string>();

  // ── Drag & drop state ──────────────────────────────────────────────────
  dragPayload = $state<DragPayload | null>(null);
  dropTarget = $state<DropTarget | null>(null);

  // ── Pending operations (for optimistic update UX) ─────────────────────
  pendingOps = new SvelteMap<string, { type: string; targetId: string }>();

  // ── Foldered session IDs (for filtering History to inbox-only) ──────
  // Tracks ALL session IDs that are assigned to any folder.
  // Updated on refresh(), assignSession(), unassignSession(), deleteFolder().
  folderedSessionIds = new SvelteSet<string>();

  // ── Dialog state ───────────────────────────────────────────────────────
  createDialogOpen = $state(false);
  editingFolderId = $state<string | null>(null);

  // ── Error toast ────────────────────────────────────────────────────────
  error = $state<string | null>(null);
  private errorTimer: ReturnType<typeof setTimeout> | null = null;

  // ── Derived ────────────────────────────────────────────────────────────

  get sortedFolders(): Folder[] {
    return [...this.folders].sort((a, b) => a.order_index - b.order_index);
  }

  get folderMap(): Map<string, Folder> {
    return new Map(this.folders.map((f) => [f.id, f]));
  }

  get isDragging(): boolean {
    return this.dragPayload !== null;
  }

  /** Check if a session is in any folder. */
  isFoldered(sessionId: string): boolean {
    return this.folderedSessionIds.has(sessionId);
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  private showError(msg: string): void {
    if (this.errorTimer) clearTimeout(this.errorTimer);
    this.error = msg;
    this.errorTimer = setTimeout(() => {
      this.error = null;
      this.errorTimer = null;
    }, 4000);
  }

  // ── Folder CRUD ────────────────────────────────────────────────────────

  getFolderById(id: string): Folder | undefined {
    return this.folderMap.get(id);
  }

  async refresh(): Promise<void> {
    this.fetchState = { status: "loading" };
    try {
      const response = await api.getFolders();
      this.folders = response.folders;
      this.fetchState = { status: "success", data: this.folders };
      // Load all foldered session IDs for History filtering
      await this.loadAllFolderedIds();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.fetchState = { status: "error", message: msg };
      this.showError(`Failed to load folders: ${msg}`);
    }
  }

  /**
   * Fetch session IDs for all folders and populate folderedSessionIds.
   * Called on refresh() to enable History → inbox filtering.
   */
  private async loadAllFolderedIds(): Promise<void> {
    try {
      const results = await Promise.all(this.folders.map((f) => api.getFolderSessions(f.id)));
      // Mutate in place — SvelteSet reassignment breaks reactivity
      this.folderedSessionIds.clear();
      for (const id of results.flatMap((sessions) => sessions.map((s) => s.id))) {
        this.folderedSessionIds.add(id);
      }
    } catch {
      // Non-critical — History will show all sessions if this fails
    }
  }

  async createFolder(request: FolderCreateRequest): Promise<Folder | null> {
    try {
      const folder = await api.createFolder(request);
      this.folders = [...this.folders, folder];
      return folder;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to create folder: ${msg}`);
      return null;
    }
  }

  async updateFolder(id: string, request: FolderUpdateRequest): Promise<Folder | null> {
    const previous = this.folders;
    this.folders = this.folders.map((f) =>
      f.id === id ? { ...f, ...request, updated_at: new Date().toISOString() } : f,
    );

    try {
      const updated = await api.updateFolder(id, request);
      this.folders = this.folders.map((f) => (f.id === id ? updated : f));
      return updated;
    } catch (e) {
      this.folders = previous;
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to update folder: ${msg}`);
      return null;
    }
  }

  async deleteFolder(id: string): Promise<boolean> {
    const previous = this.folders;
    // Get sessions from cache before deleting folder
    const folderSessions = this.folderSessions.get(id) ?? [];
    this.folders = this.folders.filter((f) => f.id !== id);

    try {
      await api.deleteFolder(id);
      // Remove foldered IDs for this folder's sessions
      for (const session of folderSessions) {
        this.folderedSessionIds.delete(session.id);
      }
      // Clean up cache
      this.folderSessions.delete(id);
      this.sessionsLoading.delete(id);
      this.sessionsError.delete(id);
      this.expandedFolders.delete(id);
      return true;
    } catch (e) {
      this.folders = previous;
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to delete folder: ${msg}`);
      return false;
    }
  }

  // ── Reorder ───────────────────────────────────────────────────────────

  /**
   * Reorder folders: move draggedId so it lands at targetId's position.
   * Optimistic — updates order_index locally, rolls back on API failure.
   */
  async reorder(draggedId: string, targetId: string, position: "before" | "after"): Promise<void> {
    const sorted = this.sortedFolders;
    const ids = sorted.map((f) => f.id);

    // Remove dragged from current position
    const filtered = ids.filter((id) => id !== draggedId);
    const targetIndex = filtered.indexOf(targetId);
    if (targetIndex === -1) return;

    const insertAt = position === "after" ? targetIndex + 1 : targetIndex;
    const newIds = [...filtered.slice(0, insertAt), draggedId, ...filtered.slice(insertAt)];

    // No-op if position didn't change
    if (JSON.stringify(newIds) === JSON.stringify(ids)) return;

    // Optimistic: update order_index locally
    const previous = this.folders;
    this.folders = this.folders.map((f) => ({
      ...f,
      order_index: newIds.indexOf(f.id),
    }));

    console.debug("[DnD] store.reorder", { draggedId, targetId, position, newIds });

    try {
      await api.reorderFolders(newIds);
    } catch (e) {
      this.folders = previous; // rollback
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Reorder failed: ${msg}`);
    }
  }

  // ── Atomic Move ───────────────────────────────────────────────────────

  /**
   * Atomically move a session from one folder to another.
   * Uses a single backend transaction — no intermediate state where
   * the session is in neither folder.
   *
   * Optimistic: updates both folder counts locally, rolls back on failure.
   */
  async moveSession(fromFolder: string, toFolder: string, sessionId: string): Promise<boolean> {
    const previous = this.folders;

    // Optimistic: decrement source, increment target
    this.folders = this.folders.map((f) => {
      if (f.id === fromFolder) return { ...f, session_count: Math.max(0, f.session_count - 1) };
      if (f.id === toFolder) return { ...f, session_count: f.session_count + 1 };
      return f;
    });
    this.pendingOps.set(sessionId, { type: "move", targetId: toFolder });

    try {
      await api.moveSessionBetweenFolders(fromFolder, toFolder, sessionId);
      // Invalidate both caches
      this.invalidateSessions(fromFolder);
      this.invalidateSessions(toFolder);
      return true;
    } catch (e) {
      this.folders = previous; // rollback
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Move failed: ${msg}`);
      return false;
    } finally {
      this.pendingOps.delete(sessionId);
    }
  }

  // ── Session Assignment ─────────────────────────────────────────────────

  async assignSession(folderId: string, sessionId: string): Promise<boolean> {
    // Optimistic: increment count + mark as foldered
    const previous = this.folders;
    this.folders = this.folders.map((f) =>
      f.id === folderId ? { ...f, session_count: f.session_count + 1 } : f,
    );
    this.folderedSessionIds.add(sessionId);
    this.pendingOps.set(sessionId, { type: "assign", targetId: folderId });

    try {
      await api.assignSessionToFolder(folderId, sessionId);
      // Invalidate cache so expanded folders re-fetch
      this.invalidateSessions(folderId);
      return true;
    } catch (e) {
      // Rollback
      this.folders = previous;
      this.folderedSessionIds.delete(sessionId);
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to assign session: ${msg}`);
      return false;
    } finally {
      this.pendingOps.delete(sessionId);
    }
  }

  async unassignSession(folderId: string, sessionId: string): Promise<boolean> {
    // Optimistic: decrement count + unmark as foldered
    const previous = this.folders;
    this.folders = this.folders.map((f) =>
      f.id === folderId ? { ...f, session_count: Math.max(0, f.session_count - 1) } : f,
    );
    this.folderedSessionIds.delete(sessionId);
    this.pendingOps.set(sessionId, { type: "unassign", targetId: folderId });

    try {
      await api.unassignSessionFromFolder(folderId, sessionId);
      this.invalidateSessions(folderId);
      return true;
    } catch (e) {
      // Rollback
      this.folders = previous;
      this.folderedSessionIds.add(sessionId);
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to unassign session: ${msg}`);
      return false;
    } finally {
      this.pendingOps.delete(sessionId);
    }
  }

  // ── Tree Assignment ─────────────────────────────────────────────────

  /**
   * Assign session tree (session + optionally children) to folder.
   */
  async assignSessionTree(
    folderId: string,
    sessionId: string,
    includeChildren: boolean = false,
  ): Promise<boolean> {
    this.pendingOps.set(sessionId, { type: "assign-tree", targetId: folderId });

    try {
      const result = await api.assignSessionTreeToFolder(folderId, sessionId, includeChildren);

      // Update local state with all assigned IDs
      for (const assignedId of result.session_ids) {
        this.folderedSessionIds.add(assignedId);
      }

      // Update folder count
      this.folders = this.folders.map((f) =>
        f.id === folderId ? { ...f, session_count: f.session_count + result.count } : f,
      );

      this.invalidateSessions(folderId);
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to assign session tree: ${msg}`);
      return false;
    } finally {
      this.pendingOps.delete(sessionId);
    }
  }

  /**
   * Unassign session tree (session + optionally children) from folder.
   */
  async unassignSessionTree(
    folderId: string,
    sessionId: string,
    includeChildren: boolean = false,
  ): Promise<boolean> {
    this.pendingOps.set(sessionId, { type: "unassign-tree", targetId: folderId });

    try {
      await api.unassignSessionTreeFromFolder(folderId, sessionId, includeChildren);

      // Update local state
      this.folderedSessionIds.delete(sessionId);
      if (includeChildren) {
        // We'd need the session store to get children, but for now just refresh
        await this.refresh();
      }

      // Update folder count (approximate - actual count comes from server)
      this.folders = this.folders.map((f) =>
        f.id === folderId ? { ...f, session_count: Math.max(0, f.session_count - 1) } : f,
      );

      this.invalidateSessions(folderId);
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.showError(`Failed to unassign session tree: ${msg}`);
      return false;
    } finally {
      this.pendingOps.delete(sessionId);
    }
  }

  // ── Session Cache ──────────────────────────────────────────────────────

  /**
   * Get sessions for a folder. Returns cached data or empty array.
   * Triggers async fetch if not cached.
   */
  getSessions(folderId: string): FolderSession[] {
    if (!this.folderSessions.has(folderId)) {
      // Defer fetch to avoid state mutation inside $derived computation.
      // Svelte 5 forbids mutating state inside $derived, $inspect, or templates.
      queueMicrotask(() => this.fetchSessions(folderId));
      return [];
    }
    return this.folderSessions.get(folderId) ?? [];
  }

  /**
   * Fetch sessions for a folder and cache them.
   * Skips if already loading (prevents duplicate fetches).
   */
  async fetchSessions(folderId: string): Promise<void> {
    if (this.sessionsLoading.get(folderId)) return;

    this.sessionsLoading.set(folderId, true);
    this.sessionsError.set(folderId, null);

    try {
      const data = await api.getFolderSessions(folderId);
      this.folderSessions.set(folderId, data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.sessionsError.set(folderId, msg);
    } finally {
      this.sessionsLoading.set(folderId, false);
    }
  }

  /**
   * Invalidate sessions cache for a folder.
   * Triggers re-fetch on next getSessions() call.
   */
  invalidateSessions(folderId: string): void {
    this.folderSessions.delete(folderId);
  }

  // ── Expand / Collapse ──────────────────────────────────────────────────

  toggleExpand(folderId: string): void {
    if (this.expandedFolders.has(folderId)) {
      this.expandedFolders.delete(folderId);
    } else {
      this.expandedFolders.add(folderId);
    }
  }

  isExpanded(folderId: string): boolean {
    return this.expandedFolders.has(folderId);
  }

  // ── Drag & Drop ────────────────────────────────────────────────────────

  startDrag(payload: DragPayload): void {
    console.debug("[DnD] store.startDrag", {
      id: payload.id,
      type: payload.type,
      sourceFolderId: payload.sourceFolderId,
    });
    this.dragPayload = payload;
  }

  endDrag(): void {
    console.debug("[DnD] store.endDrag", { wasDragging: this.dragPayload?.id });
    this.dragPayload = null;
    this.dropTarget = null;
  }

  setDropTarget(target: DropTarget | null): void {
    const prev = this.dropTarget?.id;
    console.debug("[DnD] store.setDropTarget", { prev, next: target?.id ?? null });
    this.dropTarget = target;
  }

  async handleDrop(): Promise<void> {
    if (!this.dragPayload || !this.dropTarget) return;

    if (this.dragPayload.type === "session" && this.dropTarget.type === "folder") {
      await this.assignSession(this.dropTarget.id, this.dragPayload.id);
    }

    this.endDrag();
  }

  // ── Dialog State ───────────────────────────────────────────────────────

  openCreateDialog(): void {
    this.createDialogOpen = true;
  }

  closeCreateDialog(): void {
    this.createDialogOpen = false;
  }

  startEditing(folderId: string): void {
    this.editingFolderId = folderId;
  }

  stopEditing(): void {
    this.editingFolderId = null;
  }

  // ── Reset (for testing) ────────────────────────────────────────────────

  reset(): void {
    this.folders = [];
    this.fetchState = { status: "idle" };
    this.folderSessions = new SvelteMap();
    this.sessionsLoading = new SvelteMap();
    this.sessionsError = new SvelteMap();
    this.expandedFolders = new SvelteSet();
    this.folderedSessionIds = new SvelteSet();
    this.dragPayload = null;
    this.dropTarget = null;
    this.createDialogOpen = false;
    this.editingFolderId = null;
    this.error = null;
    if (this.errorTimer) {
      clearTimeout(this.errorTimer);
      this.errorTimer = null;
    }
  }
}

// Singleton
export const folderStore = new FolderStore();

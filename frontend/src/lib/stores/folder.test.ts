/**
 * folder.test.ts
 * ==============
 * Unit tests for the class-based FolderStore.
 *
 * Tests cover:
 *   - assignSession: optimistic update, rollback on error, cache invalidation
 *   - unassignSession: optimistic update, rollback on error
 *   - getSessions: lazy fetch, cache hit, duplicate fetch prevention
 *   - invalidateSessions: cache clearing
 *   - expand/collapse: toggleExpand, isExpanded
 *   - CRUD: createFolder, updateFolder, deleteFolder with optimistic updates
 *   - Error handling: showError with auto-dismiss
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "$lib/api";
import type { Folder } from "$lib/api";
import { SvelteMap } from "svelte/reactivity";

// Mock the API module
vi.mock("$lib/api", () => ({
  api: {
    getFolders: vi.fn(),
    createFolder: vi.fn(),
    updateFolder: vi.fn(),
    deleteFolder: vi.fn(),
    assignSessionToFolder: vi.fn(),
    unassignSessionFromFolder: vi.fn(),
    getFolderSessions: vi.fn(),
  },
}));

// We need to import the store AFTER the mock is set up
// The store is a singleton, so we need to reset it between tests
let folderStore: typeof import("./folder.svelte").folderStore;

beforeEach(async () => {
  // Re-import to get fresh singleton (vitest caches modules, so we use dynamic import)
  vi.resetModules();
  const mod = await import("./folder.svelte");
  folderStore = mod.folderStore;

  // Use the store's own reset method
  folderStore.reset();

  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeFolder(overrides: Partial<Folder> = {}): Folder {
  return {
    id: "f1",
    name: "Test Folder",
    color: "#3B82F6",
    icon: "📁",
    parent_id: null,
    order_index: 0,
    session_count: 0,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// assignSession
// ---------------------------------------------------------------------------

describe("FolderStore.assignSession", () => {
  it("should optimistically increment session_count", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 0 })];
    vi.mocked(api.assignSessionToFolder).mockResolvedValue({ assigned: true });

    // Act
    const promise = folderStore.assignSession("f1", "s1");

    // Assert — optimistic update happens synchronously
    expect(folderStore.folders[0].session_count).toBe(1);

    await promise;
  });

  it("should rollback on API error", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 0 })];
    vi.mocked(api.assignSessionToFolder).mockRejectedValue(new Error("Network error"));

    // Act
    const result = await folderStore.assignSession("f1", "s1");

    // Assert
    expect(result).toBe(false);
    expect(folderStore.folders[0].session_count).toBe(0);
    expect(folderStore.error).toContain("Failed to assign session");
  });

  it("should invalidate sessions cache on success", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 0 })];
    folderStore.folderSessions = new SvelteMap([
      ["f1", [{ id: "s1", title: "Test", updated_at: "" }]],
    ]);
    vi.mocked(api.assignSessionToFolder).mockResolvedValue({ assigned: true });

    // Act
    await folderStore.assignSession("f1", "s1");

    // Assert — cache should be cleared for this folder
    expect(folderStore.folderSessions.has("f1")).toBe(false);
  });

  it("should return true on success", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 0 })];
    vi.mocked(api.assignSessionToFolder).mockResolvedValue({ assigned: true });

    // Act
    const result = await folderStore.assignSession("f1", "s1");

    // Assert
    expect(result).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// unassignSession
// ---------------------------------------------------------------------------

describe("FolderStore.unassignSession", () => {
  it("should optimistically decrement session_count", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 3 })];
    vi.mocked(api.unassignSessionFromFolder).mockResolvedValue(undefined);

    // Act
    const promise = folderStore.unassignSession("f1", "s1");

    // Assert — optimistic update
    expect(folderStore.folders[0].session_count).toBe(2);

    await promise;
  });

  it("should not go below zero", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 0 })];
    vi.mocked(api.unassignSessionFromFolder).mockResolvedValue(undefined);

    // Act
    await folderStore.unassignSession("f1", "s1");

    // Assert
    expect(folderStore.folders[0].session_count).toBe(0);
  });

  it("should rollback on API error", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", session_count: 3 })];
    vi.mocked(api.unassignSessionFromFolder).mockRejectedValue(new Error("Network error"));

    // Act
    const result = await folderStore.unassignSession("f1", "s1");

    // Assert
    expect(result).toBe(false);
    expect(folderStore.folders[0].session_count).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// getSessions / fetchSessions
// ---------------------------------------------------------------------------

describe("FolderStore.getSessions", () => {
  it("should return cached data if available", () => {
    // Arrange
    const sessions = [{ id: "s1", title: "Test Session", updated_at: "2025-01-01" }];
    folderStore.folderSessions = new SvelteMap([["f1", sessions]]);

    // Act
    const result = folderStore.getSessions("f1");

    // Assert
    expect(result).toEqual(sessions);
  });

  it("should return empty array and trigger fetch if not cached", async () => {
    // Arrange
    const fetchSpy = vi.spyOn(folderStore, "fetchSessions");
    vi.mocked(api.getFolderSessions).mockResolvedValue([]);

    // Act
    const result = folderStore.getSessions("f1");

    // Assert — empty array returned immediately
    expect(result).toEqual([]);
    // fetchSessions is deferred via queueMicrotask, flush it
    await vi.waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith("f1");
    });
  });

  it("should not trigger duplicate fetch if already loading", async () => {
    // Arrange
    vi.mocked(api.getFolderSessions).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve([]), 100)),
    );

    // Act — call getSessions twice
    folderStore.getSessions("f1");
    folderStore.getSessions("f1");

    // Assert — API should only be called once (microtask deduped by sessionsLoading guard)
    await vi.waitFor(() => {
      expect(api.getFolderSessions).toHaveBeenCalledTimes(1);
    });
  });

  it("should populate cache after successful fetch", async () => {
    // Arrange
    const sessions = [{ id: "s1", title: "Test", updated_at: "2025-01-01" }];
    vi.mocked(api.getFolderSessions).mockResolvedValue(sessions);

    // Act
    await folderStore.fetchSessions("f1");

    // Assert
    expect(folderStore.folderSessions.get("f1")).toEqual(sessions);
    expect(folderStore.sessionsLoading.get("f1")).toBe(false);
  });

  it("should set error on fetch failure", async () => {
    // Arrange
    vi.mocked(api.getFolderSessions).mockRejectedValue(new Error("Network error"));

    // Act
    await folderStore.fetchSessions("f1");

    // Assert
    expect(folderStore.sessionsError.get("f1")).toBe("Network error");
    expect(folderStore.sessionsLoading.get("f1")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// invalidateSessions
// ---------------------------------------------------------------------------

describe("FolderStore.invalidateSessions", () => {
  it("should remove folder from cache", () => {
    // Arrange
    folderStore.folderSessions = new SvelteMap([
      ["f1", [{ id: "s1", title: "Test", updated_at: "" }]],
      ["f2", [{ id: "s2", title: "Other", updated_at: "" }]],
    ]);

    // Act
    folderStore.invalidateSessions("f1");

    // Assert
    expect(folderStore.folderSessions.has("f1")).toBe(false);
    expect(folderStore.folderSessions.has("f2")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// expand / collapse
// ---------------------------------------------------------------------------

describe("FolderStore.expand/collapse", () => {
  it("should toggle expand state", () => {
    // Initially collapsed
    expect(folderStore.isExpanded("f1")).toBe(false);

    // Toggle to expanded
    folderStore.toggleExpand("f1");
    expect(folderStore.isExpanded("f1")).toBe(true);

    // Toggle back to collapsed
    folderStore.toggleExpand("f1");
    expect(folderStore.isExpanded("f1")).toBe(false);
  });

  it("should track multiple expanded folders independently", () => {
    folderStore.toggleExpand("f1");
    folderStore.toggleExpand("f2");

    expect(folderStore.isExpanded("f1")).toBe(true);
    expect(folderStore.isExpanded("f2")).toBe(true);
    expect(folderStore.isExpanded("f3")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// CRUD: createFolder
// ---------------------------------------------------------------------------

describe("FolderStore.createFolder", () => {
  it("should add folder to local state on success", async () => {
    // Arrange
    const newFolder = makeFolder({ id: "f2", name: "New Folder" });
    vi.mocked(api.createFolder).mockResolvedValue(newFolder);

    // Act
    const result = await folderStore.createFolder({ name: "New Folder" });

    // Assert
    expect(result).toEqual(newFolder);
    expect(folderStore.folders).toContainEqual(newFolder);
  });

  it("should return null on error", async () => {
    // Arrange
    vi.mocked(api.createFolder).mockRejectedValue(new Error("Duplicate name"));

    // Act
    const result = await folderStore.createFolder({ name: "Duplicate" });

    // Assert
    expect(result).toBeNull();
    expect(folderStore.error).toContain("Failed to create folder");
  });
});

// ---------------------------------------------------------------------------
// CRUD: deleteFolder
// ---------------------------------------------------------------------------

describe("FolderStore.deleteFolder", () => {
  it("should optimistically remove folder from local state", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1" }), makeFolder({ id: "f2" })];
    vi.mocked(api.deleteFolder).mockResolvedValue(undefined);

    // Act
    const promise = folderStore.deleteFolder("f1");

    // Assert — optimistic removal
    expect(folderStore.folders).toHaveLength(1);
    expect(folderStore.folders[0].id).toBe("f2");

    await promise;
  });

  it("should rollback on API error", async () => {
    // Arrange
    const folders = [makeFolder({ id: "f1" }), makeFolder({ id: "f2" })];
    folderStore.folders = [...folders];
    vi.mocked(api.deleteFolder).mockRejectedValue(new Error("Server error"));

    // Act
    const result = await folderStore.deleteFolder("f1");

    // Assert
    expect(result).toBe(false);
    expect(folderStore.folders).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// CRUD: updateFolder
// ---------------------------------------------------------------------------

describe("FolderStore.updateFolder", () => {
  it("should optimistically update folder fields", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", name: "Old Name" })];
    const updated = makeFolder({ id: "f1", name: "New Name" });
    vi.mocked(api.updateFolder).mockResolvedValue(updated);

    // Act
    const promise = folderStore.updateFolder("f1", { name: "New Name" });

    // Assert — optimistic update
    expect(folderStore.folders[0].name).toBe("New Name");

    const result = await promise;
    expect(result?.name).toBe("New Name");
  });

  it("should rollback on API error", async () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", name: "Old Name" })];
    vi.mocked(api.updateFolder).mockRejectedValue(new Error("Server error"));

    // Act
    const result = await folderStore.updateFolder("f1", { name: "New Name" });

    // Assert
    expect(result).toBeNull();
    expect(folderStore.folders[0].name).toBe("Old Name");
  });
});

// ---------------------------------------------------------------------------
// sortedFolders / getFolderById
// ---------------------------------------------------------------------------

describe("FolderStore.derived", () => {
  it("sortedFolders should return folders sorted by order_index", () => {
    // Arrange
    folderStore.folders = [
      makeFolder({ id: "f1", order_index: 2 }),
      makeFolder({ id: "f2", order_index: 0 }),
      makeFolder({ id: "f3", order_index: 1 }),
    ];

    // Assert
    const sorted = folderStore.sortedFolders;
    expect(sorted.map((f) => f.id)).toEqual(["f2", "f3", "f1"]);
  });

  it("getFolderById should return folder by id", () => {
    // Arrange
    folderStore.folders = [makeFolder({ id: "f1", name: "My Folder" })];

    // Assert
    expect(folderStore.getFolderById("f1")?.name).toBe("My Folder");
    expect(folderStore.getFolderById("nonexistent")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// drag & drop
// ---------------------------------------------------------------------------

describe("FolderStore.drag & drop", () => {
  it("should track drag state", () => {
    expect(folderStore.isDragging).toBe(false);

    folderStore.startDrag({ type: "session", id: "s1", title: "Test" });
    expect(folderStore.isDragging).toBe(true);
    expect(folderStore.dragPayload?.id).toBe("s1");

    folderStore.endDrag();
    expect(folderStore.isDragging).toBe(false);
    expect(folderStore.dragPayload).toBeNull();
    expect(folderStore.dropTarget).toBeNull();
  });

  it("should track drop target", () => {
    folderStore.setDropTarget({ type: "folder", id: "f1" });
    expect(folderStore.dropTarget?.id).toBe("f1");

    folderStore.setDropTarget(null);
    expect(folderStore.dropTarget).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// isFoldered / folderedSessionIds
// ---------------------------------------------------------------------------

describe("FolderStore.isFoldered", () => {
  it("should return false for unknown session", () => {
    expect(folderStore.isFoldered("s999")).toBe(false);
  });

  it("should return true after assignSession succeeds", async () => {
    folderStore.folders = [makeFolder()];
    vi.mocked(api.assignSessionToFolder).mockResolvedValue({ assigned: true });

    await folderStore.assignSession("f1", "s1");

    expect(folderStore.isFoldered("s1")).toBe(true);
  });

  it("should return false after unassignSession succeeds", async () => {
    folderStore.folders = [makeFolder()];
    folderStore.folderedSessionIds.add("s1");
    vi.mocked(api.unassignSessionFromFolder).mockResolvedValue(undefined);

    await folderStore.unassignSession("f1", "s1");

    expect(folderStore.isFoldered("s1")).toBe(false);
  });

  it("should rollback isFoldered on assign error", async () => {
    folderStore.folders = [makeFolder({ session_count: 0 })];
    vi.mocked(api.assignSessionToFolder).mockRejectedValue(new Error("fail"));

    await folderStore.assignSession("f1", "s1");

    expect(folderStore.isFoldered("s1")).toBe(false);
  });

  it("should rollback isFoldered on unassign error", async () => {
    folderStore.folders = [makeFolder({ session_count: 1 })];
    folderStore.folderedSessionIds.add("s1");
    vi.mocked(api.unassignSessionFromFolder).mockRejectedValue(new Error("fail"));

    await folderStore.unassignSession("f1", "s1");

    expect(folderStore.isFoldered("s1")).toBe(true);
  });

  it("should track multiple sessions independently", async () => {
    folderStore.folders = [makeFolder()];
    vi.mocked(api.assignSessionToFolder).mockResolvedValue({ assigned: true });

    await folderStore.assignSession("f1", "s1");
    await folderStore.assignSession("f1", "s2");

    expect(folderStore.isFoldered("s1")).toBe(true);
    expect(folderStore.isFoldered("s2")).toBe(true);
    expect(folderStore.isFoldered("s3")).toBe(false);
  });

  it("should clear folderedSessionIds on reset", () => {
    folderStore.folderedSessionIds.add("s1");
    folderStore.folderedSessionIds.add("s2");

    folderStore.reset();

    expect(folderStore.isFoldered("s1")).toBe(false);
    expect(folderStore.isFoldered("s2")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// deleteFolder should clean up folderedSessionIds
// ---------------------------------------------------------------------------

describe("FolderStore.deleteFolder — folderedSessionIds cleanup", () => {
  it("should remove foldered IDs for deleted folder sessions", async () => {
    const sessions = [
      { id: "s1", title: "Session 1", updated_at: "" },
      { id: "s2", title: "Session 2", updated_at: "" },
    ];
    folderStore.folders = [makeFolder({ id: "f1" })];
    folderStore.folderSessions = new SvelteMap([["f1", sessions]]);
    folderStore.folderedSessionIds.add("s1");
    folderStore.folderedSessionIds.add("s2");
    vi.mocked(api.deleteFolder).mockResolvedValue(undefined);

    const result = await folderStore.deleteFolder("f1");

    expect(result).toBe(true);
    expect(folderStore.isFoldered("s1")).toBe(false);
    expect(folderStore.isFoldered("s2")).toBe(false);
  });

  it("should NOT remove foldered IDs on delete error (rollback)", async () => {
    const sessions = [{ id: "s1", title: "Session 1", updated_at: "" }];
    folderStore.folders = [makeFolder({ id: "f1" })];
    folderStore.folderSessions = new SvelteMap([["f1", sessions]]);
    folderStore.folderedSessionIds.add("s1");
    vi.mocked(api.deleteFolder).mockRejectedValue(new Error("Server error"));

    const result = await folderStore.deleteFolder("f1");

    expect(result).toBe(false);
    expect(folderStore.isFoldered("s1")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// refresh should populate folderedSessionIds
// ---------------------------------------------------------------------------

describe("FolderStore.refresh — loadAllFolderedIds", () => {
  it("should populate folderedSessionIds from API", async () => {
    const folders = [makeFolder({ id: "f1" }), makeFolder({ id: "f2" })];
    vi.mocked(api.getFolders).mockResolvedValue({ folders });
    vi.mocked(api.getFolderSessions)
      .mockResolvedValueOnce([{ id: "s1", title: "A", updated_at: "" }])
      .mockResolvedValueOnce([
        { id: "s2", title: "B", updated_at: "" },
        { id: "s3", title: "C", updated_at: "" },
      ]);

    await folderStore.refresh();

    expect(folderStore.isFoldered("s1")).toBe(true);
    expect(folderStore.isFoldered("s2")).toBe(true);
    expect(folderStore.isFoldered("s3")).toBe(true);
    expect(folderStore.isFoldered("s999")).toBe(false);
  });
});

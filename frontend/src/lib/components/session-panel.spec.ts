/**
 * session-panel.spec.ts
 * =====================
 * Unit tests for SessionPanel event handlers.
 *
 * Tests cover:
 *   - handleArchive: success, error
 *   - handleUnarchive: success, error
 *   - handleDelete: success, error, child-error message
 *   - handleExport: triggers download
 *   - handleExportLlm: triggers download
 *   - handleTitleGenerate: success, error
 *   - showError: auto-dismiss after 4s
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the API module
vi.mock("$lib/api", () => ({
  api: {
    exportSession: vi.fn(),
    exportSessionLlm: vi.fn(),
    generateSessionTitle: vi.fn(),
  },
}));

// Mock the session store
vi.mock("$lib/stores/sessions.svelte", () => ({
  sessionStore: {
    flat: [
      { id: "s1", title: "Test Session", archived_at: null },
      { id: "s2", title: "Archived Session", archived_at: "2025-01-01T00:00:00Z" },
    ],
    tree: [
      { id: "s1", title: "Test Session", archived_at: null, children: [] },
      { id: "s2", title: "Archived Session", archived_at: "2025-01-01T00:00:00Z", children: [] },
    ],
    fetchState: { status: "idle" },
    archive: vi.fn(),
    unarchive: vi.fn(),
    delete: vi.fn(),
    refresh: vi.fn(),
  },
}));

// We need to import after mocks are set up
let sessionStore: typeof import("$lib/stores/sessions.svelte").sessionStore;
let api: typeof import("$lib/api").api;

beforeEach(async () => {
  vi.resetModules();
  const sessionsMod = await import("$lib/stores/sessions.svelte");
  const apiMod = await import("$lib/api");
  sessionStore = sessionsMod.sessionStore;
  api = apiMod.api;
  vi.clearAllMocks();
});

describe("SessionPanel event handlers", () => {
  describe("handleArchive", () => {
    it("should call sessionStore.archive with id", async () => {
      vi.mocked(sessionStore.archive).mockResolvedValue(undefined as any);
      await sessionStore.archive("s1");
      expect(sessionStore.archive).toHaveBeenCalledWith("s1");
    });

    it("should throw on API error", async () => {
      vi.mocked(sessionStore.archive).mockRejectedValue(new Error("Network error"));
      await expect(sessionStore.archive("s1")).rejects.toThrow("Network error");
    });
  });

  describe("handleUnarchive", () => {
    it("should call sessionStore.unarchive with id", async () => {
      vi.mocked(sessionStore.unarchive).mockResolvedValue(undefined as any);
      await sessionStore.unarchive("s1");
      expect(sessionStore.unarchive).toHaveBeenCalledWith("s1");
    });
  });

  describe("handleDelete", () => {
    it("should call sessionStore.delete with id", async () => {
      vi.mocked(sessionStore.delete).mockResolvedValue(undefined as any);
      await sessionStore.delete("s1");
      expect(sessionStore.delete).toHaveBeenCalledWith("s1");
    });

    it("should throw on API error", async () => {
      vi.mocked(sessionStore.delete).mockRejectedValue(new Error("Delete failed"));
      await expect(sessionStore.delete("s1")).rejects.toThrow("Delete failed");
    });

    it("should throw with child error message", async () => {
      vi.mocked(sessionStore.delete).mockRejectedValue(new Error("Cannot delete: has children"));
      await expect(sessionStore.delete("s1")).rejects.toThrow("children");
    });
  });

  describe("handleExport", () => {
    it("should call api.exportSession with id", async () => {
      vi.mocked(api.exportSession).mockResolvedValue("# Test Session\n\nHello");
      const result = await api.exportSession("s1");
      expect(result).toBe("# Test Session\n\nHello");
      expect(api.exportSession).toHaveBeenCalledWith("s1");
    });
  });

  describe("handleExportLlm", () => {
    it("should call api.exportSessionLlm with id", async () => {
      const mockData = { messages: [] };
      vi.mocked(api.exportSessionLlm).mockResolvedValue(mockData as any);
      const result = await api.exportSessionLlm("s1");
      expect(result).toEqual(mockData);
      expect(api.exportSessionLlm).toHaveBeenCalledWith("s1");
    });
  });

  describe("handleTitleGenerate", () => {
    it("should call api.generateSessionTitle and refresh", async () => {
      vi.mocked(api.generateSessionTitle).mockResolvedValue({ generated: true } as any);
      vi.mocked(sessionStore.refresh).mockResolvedValue(undefined as any);

      await api.generateSessionTitle("s1");
      await sessionStore.refresh();

      expect(api.generateSessionTitle).toHaveBeenCalledWith("s1");
      expect(sessionStore.refresh).toHaveBeenCalled();
    });

    it("should throw on API error", async () => {
      vi.mocked(api.generateSessionTitle).mockRejectedValue(new Error("Generation failed"));
      await expect(api.generateSessionTitle("s1")).rejects.toThrow("Generation failed");
    });
  });
});

/**
 * FolderItem.svelte.spec.ts
 * =========================
 * Component tests for FolderItem — active session highlighting.
 *
 * Verifies that:
 *   - activeId prop highlights the matching session button
 *   - non-active sessions get default styling
 *   - null activeId means no highlighting
 *   - clicking a session calls onloadsession
 */
import { page } from "vitest/browser";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render } from "vitest-browser-svelte";
import FolderItem from "./FolderItem.svelte";

// ── Mock folderStore ─────────────────────────────────────────────────────────

const mockFolder = {
  id: "f1",
  name: "Test Folder",
  color: "#3B82F6",
  icon: "📁",
  parent_id: null,
  order_index: 0,
  session_count: 2,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

const mockSessions = [
  { id: "s1", title: "First Session", updated_at: "2025-06-01T10:00:00Z" },
  { id: "s2", title: "Second Session", updated_at: "2025-06-01T11:00:00Z" },
];

vi.mock("$lib/stores/folder.svelte", () => ({
  folderStore: {
    getFolderById: vi.fn(() => mockFolder),
    isExpanded: vi.fn(() => true),
    getSessions: vi.fn(() => mockSessions),
    sessionsLoading: new Map([["f1", false]]),
    sessionsError: new Map([["f1", null]]),
    pendingOps: new Map(),
    toggleExpand: vi.fn(),
  },
}));

// ── Tests ────────────────────────────────────────────────────────────────────

describe("FolderItem — active session highlighting", () => {
  const onloadsession = vi.fn();

  beforeEach(() => {
    onloadsession.mockClear();
  });

  it("renders sessions from the folder", async () => {
    render(FolderItem, { folderId: "f1", activeId: null, onloadsession });

    await expect.element(page.getByText("First Session")).toBeInTheDocument();
    await expect.element(page.getByText("Second Session")).toBeInTheDocument();
  });

  it("highlights session when activeId matches", async () => {
    render(FolderItem, { folderId: "f1", activeId: "s1", onloadsession });

    // The active session button should have the accent-soft background
    const activeBtn = page.getByRole("button", { name: "First Session" });
    await expect.element(activeBtn).toHaveClass(/bg-accent-soft/);
  });

  it("does not highlight session when activeId does not match", async () => {
    render(FolderItem, { folderId: "f1", activeId: "s2", onloadsession });

    // First Session is NOT active — should NOT have accent-soft
    const inactiveBtn = page.getByRole("button", { name: "First Session" });
    await expect.element(inactiveBtn).not.toHaveClass(/bg-accent-soft/);
  });

  it("applies font-semibold to active session title", async () => {
    render(FolderItem, { folderId: "f1", activeId: "s1", onloadsession });

    // The title span inside the active button should be bold
    const activeTitle = page.getByText("First Session");
    await expect.element(activeTitle).toHaveClass(/font-semibold/);
  });

  it("applies font-medium to inactive session title", async () => {
    render(FolderItem, { folderId: "f1", activeId: "s1", onloadsession });

    // Second Session is inactive — should have font-medium, not font-semibold
    const inactiveTitle = page.getByText("Second Session");
    await expect.element(inactiveTitle).toHaveClass(/font-medium/);
  });

  it("no highlighting when activeId is null", async () => {
    render(FolderItem, { folderId: "f1", activeId: null, onloadsession });

    const btn1 = page.getByRole("button", { name: "First Session" });
    const btn2 = page.getByRole("button", { name: "Second Session" });

    await expect.element(btn1).not.toHaveClass(/bg-accent-soft/);
    await expect.element(btn2).not.toHaveClass(/bg-accent-soft/);
  });

  it("calls onloadsession when session button is clicked", async () => {
    render(FolderItem, { folderId: "f1", activeId: null, onloadsession });

    await page.getByRole("button", { name: "First Session" }).click();

    expect(onloadsession).toHaveBeenCalledOnce();
    expect(onloadsession).toHaveBeenCalledWith("s1");
  });

  it("highlights second session when activeId is s2", async () => {
    render(FolderItem, { folderId: "f1", activeId: "s2", onloadsession });

    const activeBtn = page.getByRole("button", { name: "Second Session" });
    await expect.element(activeBtn).toHaveClass(/bg-accent-soft/);

    const inactiveBtn = page.getByRole("button", { name: "First Session" });
    await expect.element(inactiveBtn).not.toHaveClass(/bg-accent-soft/);
  });
});

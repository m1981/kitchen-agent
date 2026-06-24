/**
 * notes-panel.spec.ts
 * ===================
 * Component tests for NotesPanel — specifically SvelteSet reactivity
 * for the selectedNoteIds toggle/select-all/clear cycle.
 *
 * Verifies that the Set → SvelteSet migration preserves reactive
 * checkbox toggling, "Insert N" button visibility, and clear-on-insert.
 */
import { page } from "vitest/browser";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render } from "vitest-browser-svelte";
import NotesPanel from "./NotesPanel.svelte";

// ── Mock notesStore ─────────────────────────────────────────────────────────

const mockNotes = [
  {
    id: "n1",
    session_id: "s1",
    selected_text: "First selected text",
    note: "My annotation",
    source_role: "user" as const,
    created_at: "2025-06-01T10:00:00Z",
  },
  {
    id: "n2",
    session_id: "s1",
    selected_text: "Second selected text",
    note: "",
    source_role: "assistant" as const,
    created_at: "2025-06-01T11:00:00Z",
  },
  {
    id: "n3",
    session_id: "s1",
    selected_text: "Third selected text",
    note: "Another note",
    source_role: "user" as const,
    created_at: "2025-06-01T12:00:00Z",
  },
];

vi.mock("$lib/stores/notes.svelte", () => ({
  notesStore: {
    load: vi.fn(),
    forSession: vi.fn(() => mockNotes),
    fetchStateFor: vi.fn(() => ({ status: "success" })),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

// ── Tests ────────────────────────────────────────────────────────────────────

describe("NotesPanel — SvelteSet reactivity", () => {
  const oninsertnotes = vi.fn();

  beforeEach(() => {
    oninsertnotes.mockClear();
  });

  it("renders all notes", async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    // All 3 notes should be visible
    await expect.element(page.getByText("First selected text")).toBeInTheDocument();
    await expect.element(page.getByText("Second selected text")).toBeInTheDocument();
    await expect.element(page.getByText("Third selected text")).toBeInTheDocument();
  });

  it("shows no Insert button initially (nothing selected)", async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    // "Insert" button should NOT be present
    await expect.element(page.getByText(/^Insert/)).not.toBeInTheDocument();
  });

  it('shows "Insert 1" after clicking one checkbox', async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    // Click first checkbox
    const checkboxes = page.getByRole("checkbox");
    await checkboxes.nth(0).click();

    // "Insert 1" button should appear
    await expect.element(page.getByText("Insert 1")).toBeInTheDocument();
  });

  it('shows "Insert 2" after clicking two checkboxes', async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    const checkboxes = page.getByRole("checkbox");
    await checkboxes.nth(0).click();
    await checkboxes.nth(1).click();

    await expect.element(page.getByText("Insert 2")).toBeInTheDocument();
  });

  it("hides Insert button after unchecking all", async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    const checkboxes = page.getByRole("checkbox");

    // Select then deselect
    await checkboxes.nth(0).click();
    await expect.element(page.getByText("Insert 1")).toBeInTheDocument();

    await checkboxes.nth(0).click();
    await expect.element(page.getByText(/^Insert/)).not.toBeInTheDocument();
  });

  it("calls oninsertnotes and clears selection on Insert click", async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    // Select 2 notes
    const checkboxes = page.getByRole("checkbox");
    await checkboxes.nth(0).click();
    await checkboxes.nth(1).click();

    // Click Insert
    await page.getByText("Insert 2").click();

    // oninsertnotes should be called with the 2 selected notes
    expect(oninsertnotes).toHaveBeenCalledOnce();
    const calledWith = oninsertnotes.mock.calls[0][0];
    expect(calledWith).toHaveLength(2);
    expect(calledWith.map((n: { id: string }) => n.id)).toEqual(["n1", "n2"]);

    // Selection should be cleared — Insert button gone
    await expect.element(page.getByText(/^Insert/)).not.toBeInTheDocument();
  });

  it("shows note count badge", async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    // Badge should show the count
    await expect.element(page.getByText("3", { exact: true })).toBeInTheDocument();
  });

  it("renders role badges correctly", async () => {
    render(NotesPanel, { sessionId: "s1", oninsertnotes });

    // Should have user and assistant role badges
    await expect.element(page.getByText("user").first()).toBeInTheDocument();
    await expect.element(page.getByText("assistant")).toBeInTheDocument();
  });
});

describe("NotesPanel — empty state", () => {
  it("shows empty state when no notes", async () => {
    // Override the mock for this test
    const { notesStore } = await import("$lib/stores/notes.svelte");
    vi.mocked(notesStore.forSession).mockReturnValueOnce([]);

    render(NotesPanel, { sessionId: "s-empty", oninsertnotes: vi.fn() });

    await expect.element(page.getByText("No notes yet")).toBeInTheDocument();
  });
});

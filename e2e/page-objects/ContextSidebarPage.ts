import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the Right Context Sidebar.
 * Handles context files, notes, and editor tabs.
 */
export class ContextSidebarPage {
    readonly page: Page;

    // ── Locators ──────────────────────────────────────────────────
    readonly panel: Locator;
    readonly contextTab: Locator;
    readonly notesTab: Locator;
    readonly editorTab: Locator;
    readonly fileList: Locator;
    readonly fileCheckboxes: Locator;
    readonly notesList: Locator;
    readonly hidePanelButton: Locator;

    constructor(page: Page) {
        this.page = page;

        // Right sidebar panel (second aside)
        this.panel = page.locator('aside').last();

        // Tabs
        this.contextTab = page.locator('button:has-text("Context")').first();
        this.notesTab = page.locator('button:has-text("Notes")').first();
        this.editorTab = page.locator('button:has-text("Editor")').first();

        // File list with checkboxes
        this.fileList = page.locator('aside').last().locator('label, [class*="file"]');
        this.fileCheckboxes = page.locator('aside').last().locator('input[type="checkbox"]');

        // Notes list
        this.notesList = page.locator('aside').last().locator('[class*="note"]');

        // Hide panel button
        this.hidePanelButton = page.locator('button:has-text("Hide panel")');
    }

    // ── Actions ───────────────────────────────────────────────────

    /**
     * Toggle the right panel visibility
     */
    async toggle() {
        await this.hidePanelButton.click();
    }

    /**
     * Check if panel is visible
     */
    async isVisible(): Promise<boolean> {
        return this.panel.isVisible();
    }

    /**
     * Switch to Context tab
     */
    async switchToContext() {
        await this.contextTab.click();
    }

    /**
     * Switch to Notes tab
     */
    async switchToNotes() {
        await this.notesTab.click();
    }

    /**
     * Switch to Editor tab
     */
    async switchToEditor() {
        await this.editorTab.click();
    }

    /**
     * Check/uncheck a context file by name
     */
    async toggleFile(filename: string) {
        const checkbox = this.page.locator(
            `aside label:has-text("${filename}") input[type="checkbox"]`
        );
        await checkbox.click();
    }

    /**
     * Get count of visible files
     */
    async getFileCount(): Promise<number> {
        return this.fileCheckboxes.count();
    }

    // ── Assertions ────────────────────────────────────────────────

    /**
     * Assert panel is visible
     */
    async expectVisible() {
        await expect(this.panel).toBeVisible();
    }

    /**
     * Assert panel is hidden
     */
    async expectHidden() {
        await expect(this.panel).toBeHidden();
    }

    /**
     * Assert a file is checked
     */
    async expectFileChecked(filename: string) {
        const checkbox = this.page.locator(
            `aside label:has-text("${filename}") input[type="checkbox"]`
        );
        await expect(checkbox).toBeChecked();
    }

    /**
     * Assert a file is unchecked
     */
    async expectFileUnchecked(filename: string) {
        const checkbox = this.page.locator(
            `aside label:has-text("${filename}") input[type="checkbox"]`
        );
        await expect(checkbox).not.toBeChecked();
    }
}

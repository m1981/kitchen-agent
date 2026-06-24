import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the Left Sidebar.
 * Handles session list, folders, and sidebar toggle interactions.
 */
export class SidebarPage {
    readonly page: Page;

    // ── Locators ──────────────────────────────────────────────────
    readonly sidebar: Locator;
    readonly toggleButton: Locator;
    readonly mobileBackdrop: Locator;
    readonly newChatButton: Locator;
    readonly sessionList: Locator;
    readonly folderTree: Locator;
    readonly archivedSection: Locator;

    constructor(page: Page) {
        this.page = page;

        // Sidebar container (first aside element)
        this.sidebar = page.locator('aside').first();

        // Toggle button in header
        this.toggleButton = page.getByTestId('sidebar-toggle');

        // Mobile backdrop overlay
        this.mobileBackdrop = page.getByTestId('mobile-backdrop');

        // New chat button
        this.newChatButton = page.locator('aside button:has-text("New chat")');

        // Session list items
        this.sessionList = page.locator('aside button[data-session-id], aside [role="listitem"]');

        // Folder tree
        this.folderTree = page.locator('[data-testid="folder-tree"], aside [class*="folder"]');

        // Archived section
        this.archivedSection = page.locator('aside button:has-text("Archived")');
    }

    // ── Actions ───────────────────────────────────────────────────

    /**
     * Toggle the sidebar visibility
     */
    async toggle() {
        await this.toggleButton.click();
    }

    /**
     * Check if sidebar is visible on screen
     */
    async isVisible(): Promise<boolean> {
        return this.sidebar.isVisible();
    }

    /**
     * Check if mobile backdrop is visible
     */
    async isBackdropVisible(): Promise<boolean> {
        return this.mobileBackdrop.isVisible();
    }

    /**
     * Click backdrop to close sidebar (mobile only)
     */
    async closeViaBackdrop() {
        await this.mobileBackdrop.click();
    }

    /**
     * Create a new chat session
     */
    async createNewChat() {
        await this.newChatButton.click();
    }

    /**
     * Get the count of sessions in the history list
     */
    async getSessionCount(): Promise<number> {
        // Count buttons that look like session items (have 3-dot menu nearby)
        const sessions = this.page
            .locator('aside')
            .first()
            .locator('button')
            .filter({
                has: this.page.locator('text=/^\\w/')
            });
        return sessions.count();
    }

    /**
     * Click on a session by its title text
     */
    async clickSession(title: string) {
        const session = this.page
            .locator('aside')
            .first()
            .locator(`button:has-text("${title}")`)
            .first();
        await session.click();
    }

    /**
     * Expand the archived section
     */
    async expandArchived() {
        const archived = this.archivedSection;
        if (await archived.isVisible()) {
            await archived.click();
        }
    }

    // ── Assertions ────────────────────────────────────────────────

    /**
     * Assert sidebar is visible
     */
    async expectVisible() {
        await expect(this.sidebar).toBeVisible();
    }

    /**
     * Assert sidebar is hidden
     */
    async expectHidden() {
        await expect(this.sidebar).toBeHidden();
    }

    /**
     * Assert toggle button has correct label
     */
    async expectToggleLabel(label: 'Hide sidebar' | 'Show sidebar') {
        await expect(this.toggleButton).toHaveAttribute('aria-label', label);
    }
}

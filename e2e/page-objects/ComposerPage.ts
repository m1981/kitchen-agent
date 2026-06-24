import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the Chat Composer.
 * Handles message input, tools toggle, model selection, and send button.
 */
export class ComposerPage {
    readonly page: Page;

    // ── Locators ──────────────────────────────────────────────────
    readonly textarea: Locator;
    readonly sendButton: Locator;
    readonly stopButton: Locator;
    readonly toolsToggle: Locator;
    readonly modelSelector: Locator;
    readonly tokenStrip: Locator;
    readonly imagePreview: Locator;
    readonly contextFilesStrip: Locator;

    constructor(page: Page) {
        this.page = page;

        // Text input
        this.textarea = page.getByTestId('chat-input');

        // Send/Stop buttons
        this.sendButton = page.getByTestId('send-btn');
        this.stopButton = page.getByTestId('stop-btn');

        // Tools toggle
        this.toolsToggle = page.getByTestId('tools-toggle');

        // Model selector dropdown
        this.modelSelector = page.getByTestId('model-selector');

        // Token usage strip (only visible when >10%)
        this.tokenStrip = page.getByTestId('token-strip');

        // Pasted image previews
        this.imagePreview = page.locator('.composer-box img, footer img');

        // Context files strip
        this.contextFilesStrip = page.locator('footer .flex:has-text("Will inject")');
    }

    // ── Actions ───────────────────────────────────────────────────

    /**
     * Type a message in the textarea
     */
    async typeMessage(text: string) {
        await this.textarea.fill(text);
    }

    /**
     * Clear the textarea
     */
    async clearMessage() {
        await this.textarea.clear();
    }

    /**
     * Send the current message (click send button or press Enter)
     */
    async send() {
        await this.sendButton.click();
    }

    /**
     * Send message via keyboard shortcut
     */
    async sendViaKeyboard() {
        await this.textarea.press('Enter');
    }

    /**
     * Stop streaming (if active)
     */
    async stop() {
        await this.stopButton.click();
    }

    /**
     * Toggle tools on/off
     */
    async toggleTools() {
        await this.toolsToggle.click();
    }

    /**
     * Select a model from the dropdown
     */
    async selectModel(modelName: string) {
        await this.modelSelector.selectOption({ label: modelName });
    }

    /**
     * Get the current textarea value
     */
    async getMessage(): Promise<string> {
        return this.textarea.inputValue();
    }

    /**
     * Get the current model selection
     */
    async getSelectedModel(): Promise<string> {
        return this.modelSelector.inputValue();
    }

    // ── State Checks ──────────────────────────────────────────────

    /**
     * Check if send button is enabled
     */
    async isSendEnabled(): Promise<boolean> {
        return this.sendButton.isEnabled();
    }

    /**
     * Check if tools are enabled
     */
    async isToolsEnabled(): Promise<boolean> {
        return this.toolsToggle.getAttribute('aria-pressed').then((v) => v === 'true');
    }

    /**
     * Check if token strip is visible
     */
    async isTokenStripVisible(): Promise<boolean> {
        return this.tokenStrip.isVisible();
    }

    // ── Assertions ────────────────────────────────────────────────

    /**
     * Assert textarea is visible and ready
     */
    async expectReady() {
        await expect(this.textarea).toBeVisible();
        await expect(this.sendButton).toBeVisible();
    }

    /**
     * Assert send button is disabled (empty input)
     */
    async expectSendDisabled() {
        await expect(this.sendButton).toBeDisabled();
    }

    /**
     * Assert send button is enabled (has input)
     */
    async expectSendEnabled() {
        await expect(this.sendButton).toBeEnabled();
    }

    /**
     * Assert tools toggle is in specific state
     */
    async expectToolsState(enabled: boolean) {
        await expect(this.toolsToggle).toHaveAttribute('aria-pressed', String(enabled));
    }

    /**
     * Assert token strip is visible
     */
    async expectTokenStripVisible() {
        await expect(this.tokenStrip).toBeVisible();
    }

    /**
     * Assert token strip is hidden
     */
    async expectTokenStripHidden() {
        await expect(this.tokenStrip).toBeHidden();
    }
}

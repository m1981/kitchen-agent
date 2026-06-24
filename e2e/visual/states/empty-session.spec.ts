import { test, expect } from '@playwright/test';
import { ChatPage } from '../../page-objects/ChatPage';
import { ComposerPage } from '../../page-objects/ComposerPage';

test.describe('Empty Session State @smoke', () => {
    let chatPage: ChatPage;
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        // Clear localStorage for consistent state
        await page.goto('/');
        await page.evaluate(() => localStorage.clear());

        chatPage = new ChatPage(page);
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('new session shows empty chat', async () => {
        // No messages
        const messageCount = await chatPage.chatBubbles.count();
        expect(messageCount).toBe(0);
    });

    test('system prompt visible with "Not set"', async ({ page }) => {
        // System prompt bubble visible
        await chatPage.expectSystemPromptVisible();

        // Should show "Not set" text
        const promptText = await chatPage.systemPrompt.textContent();
        expect(promptText).toContain('Not set');
    });

    test('system prompt expands on click', async ({ page }) => {
        // Click to expand
        await chatPage.systemPromptToggle.click();

        // Should show expanded content (pre or textarea)
        const expandedContent = chatPage.systemPrompt.locator('pre, p');
        await expect(expandedContent.first()).toBeVisible();
    });

    test('composer ready with placeholder text', async () => {
        await composerPage.expectReady();

        // Placeholder should mention layouts, materials, etc.
        const placeholder = await composerPage.textarea.getAttribute('placeholder');
        expect(placeholder).toContain('layouts');
    });

    test('send button disabled when empty', async () => {
        await composerPage.expectSendDisabled();
    });

    test('token strip hidden when usage is zero', async () => {
        await composerPage.expectTokenStripHidden();
    });
});

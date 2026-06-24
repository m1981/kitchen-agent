import { test, expect } from '@playwright/test';
import { ChatPage } from '../../page-objects/ChatPage';

test.describe('System Prompt Bubble @smoke @regression', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);

        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('system prompt bubble is visible', async () => {
        await chatPage.expectSystemPromptVisible();
    });

    test('collapsed by default (single line)', async () => {
        await chatPage.expectSystemPromptCollapsed();
    });

    test('shows mode badge', async () => {
        const text = await chatPage.systemPrompt.textContent();
        expect(text).toContain('General');
    });

    test('shows "Not set" when no override', async () => {
        const text = await chatPage.systemPrompt.textContent();
        expect(text).toContain('Not set');
    });

    test('expand button (chevron) is visible', async () => {
        const chevron = chatPage.systemPrompt.locator('svg').last();
        await expect(chevron).toBeVisible();
    });

    test('click expand shows full content', async () => {
        // Click the header to expand
        await chatPage.systemPromptToggle.click();

        // Should show expanded content
        const expandedContent = chatPage.systemPrompt.locator('pre, p').first();
        await expect(expandedContent).toBeVisible();
    });

    test('edit button is visible', async () => {
        const editBtn = chatPage.systemPrompt.locator('[aria-label="Edit system prompt"]');
        await expect(editBtn).toBeVisible();
    });

    test('click edit opens textarea', async () => {
        const editBtn = chatPage.systemPrompt.locator('[aria-label="Edit system prompt"]');
        await editBtn.click();

        // Textarea should appear
        const textarea = chatPage.systemPrompt.locator('textarea');
        await expect(textarea).toBeVisible();
    });

    test('cancel edit closes textarea', async () => {
        // Start editing
        const editBtn = chatPage.systemPrompt.locator('[aria-label="Edit system prompt"]');
        await editBtn.click();

        // Cancel
        const cancelBtn = chatPage.systemPrompt.locator('button:has-text("Cancel")');
        await cancelBtn.click();

        // Textarea should be hidden
        const textarea = chatPage.systemPrompt.locator('textarea');
        await expect(textarea).toBeHidden();
    });
});

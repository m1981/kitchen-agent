import { test, expect } from '@playwright/test';
import { ChatPage } from '../../page-objects/ChatPage';
import { ComposerPage } from '../../page-objects/ComposerPage';

test.describe('Message Editing @regression', () => {
    let chatPage: ChatPage;
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.evaluate(() => localStorage.clear());
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Send a message first
        await composerPage.typeMessage('Original message for editing');
        await composerPage.send();
        // Wait for user message to appear (not assistant response)
        await page.waitForSelector('[data-chat-bubble="user"]', { timeout: 10_000 });
    });

    test('edit button appears on user message hover', async () => {
        // Find a user message
        const userMessage = chatPage.userBubbles.first();

        // Hover over it
        await userMessage.hover();

        // Edit button should be visible
        const editBtn = userMessage.locator('[data-testid="edit-btn"]');
        await expect(editBtn).toBeVisible();
    });

    test('click edit opens inline editor', async () => {
        // Find edit button on first user message
        const editBtn = chatPage.userBubbles.first().locator('[data-testid="edit-btn"]');

        // Click edit
        await editBtn.click();

        // Textarea should appear
        const editor = chatPage.page.locator('textarea').last();
        await expect(editor).toBeVisible();
    });

    test('cancel edit reverts to original', async () => {
        // Start editing
        const editBtn = chatPage.userBubbles.first().locator('[data-testid="edit-btn"]');
        await editBtn.click();

        // Find cancel button
        const cancelBtn = chatPage.page.locator('button:has-text("Cancel")');
        await cancelBtn.click();

        // Original message should still be there
        await expect(chatPage.userBubbles.first()).toContainText('Original message');
    });
});

test.describe('Message Deletion @regression', () => {
    let chatPage: ChatPage;
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.evaluate(() => localStorage.clear());
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Send a message
        await composerPage.typeMessage('Message to delete');
        await composerPage.send();
        await page.waitForSelector('[data-chat-bubble="user"]', { timeout: 10_000 });
    });

    test('delete button appears on message hover', async () => {
        const message = chatPage.chatBubbles.first();
        await message.hover();

        const deleteBtn = message.locator('[data-testid="more-options-btn"]');
        await expect(deleteBtn).toBeVisible();
    });

    test('click delete shows confirm dialog', async () => {
        // Click more options
        const moreBtn = chatPage.chatBubbles.first().locator('[data-testid="more-options-btn"]');
        await moreBtn.click();

        // Click delete
        const deleteBtn = chatPage.page.locator('[data-testid="delete-btn"]').first();
        await deleteBtn.click();

        // Confirm dialog should appear
        await chatPage.expectConfirmDialogVisible();
    });

    test('cancel delete keeps message', async () => {
        const initialCount = await chatPage.getMessageCount();

        // Click more options
        const moreBtn = chatPage.chatBubbles.first().locator('[data-testid="more-options-btn"]');
        await moreBtn.click();

        // Click delete
        const deleteBtn = chatPage.page.locator('[data-testid="delete-btn"]').first();
        await deleteBtn.click();

        // Cancel
        await chatPage.confirmCancelButton.click();

        // Dialog should close
        await chatPage.expectConfirmDialogHidden();

        // Message count should be same
        const finalCount = await chatPage.getMessageCount();
        expect(finalCount).toBe(initialCount);
    });
});

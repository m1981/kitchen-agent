import { test, expect } from '@playwright/test';
import { ChatPage } from '../../page-objects/ChatPage';
import { ComposerPage } from '../../page-objects/ComposerPage';

test.describe('Chat Messaging @regression', () => {
    let chatPage: ChatPage;
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('message count updates after send', async () => {
        const initialCount = await chatPage.getMessageCount();

        // Type and send a message
        await composerPage.typeMessage('Hello, this is a test message');
        await composerPage.send();

        // Wait for user message to appear
        await chatPage.waitForMessagesLoaded(initialCount + 1);

        // Count should increase by 1 (user message)
        const newCount = await chatPage.getMessageCount();
        expect(newCount).toBeGreaterThanOrEqual(initialCount + 1);
    });

    test('user message appears on right side', async ({ page }) => {
        await composerPage.typeMessage('Test message');
        await composerPage.send();

        // Wait for user message to appear
        await page.waitForSelector('[data-chat-bubble="user"]', { timeout: 10_000 });

        // Last message should be user role
        const lastBubble = chatPage.chatBubbles.last();
        const role = await lastBubble.getAttribute('data-chat-bubble');
        expect(role).toBe('user');
    });

    test('send button disabled when input is empty', async () => {
        await composerPage.expectSendDisabled();
    });

    test('send button enabled when input has text', async () => {
        await composerPage.typeMessage('Hello');
        await composerPage.expectSendEnabled();
    });

    test('input clears after send', async () => {
        await composerPage.typeMessage('Test message');
        await composerPage.send();

        // Wait for input to clear
        await expect(chatPage.chatInput).toHaveValue('');
    });

    test('placeholder text is descriptive', async () => {
        const placeholder = await composerPage.textarea.getAttribute('placeholder');
        expect(placeholder).toContain('layouts');
        expect(placeholder).toContain('materials');
    });
});

test.describe('Message Display @regression', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('system prompt bubble shows mode badge', async () => {
        // System prompt should have mode badge
        const promptText = await chatPage.systemPrompt.textContent();
        expect(promptText).toContain('General');
    });

    test('header shows session title', async ({ page }) => {
        // Wait for header to render
        await page.waitForSelector('header', { timeout: 5_000 });
        const titleText = await chatPage.headerTitle.textContent();
        expect(titleText).toBeTruthy();
        expect(titleText?.length).toBeGreaterThan(0);
    });

    test('header shows mode badge', async () => {
        await expect(chatPage.headerModeBadge).toBeVisible();
    });
});

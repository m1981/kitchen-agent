import { test, expect } from '@playwright/test';
import { ChatPage } from '../../page-objects/ChatPage';
import { SidebarPage } from '../../page-objects/SidebarPage';
import { ComposerPage } from '../../page-objects/ComposerPage';

test.describe('Desktop Layout @smoke @desktop', () => {
    let chatPage: ChatPage;
    let sidebarPage: SidebarPage;
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        // Clear localStorage for consistent state
        await page.goto('/');
        await page.evaluate(() => localStorage.clear());

        chatPage = new ChatPage(page);
        sidebarPage = new SidebarPage(page);
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('three-panel layout renders correctly', async ({ page }) => {
        // Left sidebar hidden by default (user toggles it open)
        await sidebarPage.expectHidden();

        // Main chat area visible
        await expect(chatPage.chatInput).toBeVisible();

        // Right sidebar visible (context panel)
        const rightPanel = page.locator('aside').last();
        await expect(rightPanel).toBeVisible();
    });

    test('sidebar toggle shows left panel', async () => {
        // Initially hidden
        await sidebarPage.expectHidden();
        await sidebarPage.expectToggleLabel('Show sidebar');

        // Toggle to show
        await sidebarPage.toggle();

        // Sidebar visible
        await sidebarPage.expectVisible();
        await sidebarPage.expectToggleLabel('Hide sidebar');
    });

    test('sidebar toggle hides left panel', async () => {
        // First show
        await sidebarPage.toggle();
        await sidebarPage.expectVisible();

        // Toggle to hide
        await sidebarPage.toggle();

        // Sidebar hidden
        await sidebarPage.expectHidden();
        await sidebarPage.expectToggleLabel('Show sidebar');
    });

    test('system prompt collapsed by default', async () => {
        // System prompt bubble visible
        await chatPage.expectSystemPromptVisible();

        // Should be collapsed (no textarea or pre visible)
        await chatPage.expectSystemPromptCollapsed();
    });

    test('composer ready for input', async () => {
        await composerPage.expectReady();
        await composerPage.expectSendDisabled();
    });

    test('tools toggle works', async () => {
        // Initially enabled (blue)
        await composerPage.expectToolsState(true);

        // Toggle off
        await composerPage.toggleTools();
        await composerPage.expectToolsState(false);

        // Toggle back on
        await composerPage.toggleTools();
        await composerPage.expectToolsState(true);
    });
});

import { test, expect } from '@playwright/test';
import { ChatPage } from '../../page-objects/ChatPage';

test.describe('URL-Based Routing @smoke', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('root URL redirects to /chat/{uuid}', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // URL should now be /chat/{uuid}
        const url = page.url();
        expect(url).toMatch(/\/chat\/[a-f0-9-]+/);
    });

    test('direct URL loads session', async ({ page }) => {
        // First get a session ID by visiting root
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        const url = page.url();
        const sessionId = url.match(/\/chat\/([a-f0-9-]+)/)?.[1];

        expect(sessionId).toBeTruthy();

        // Now navigate directly to that session
        await page.goto(`/chat/${sessionId}`);
        await page.waitForLoadState('networkidle');

        // Should load without error
        const currentUrl = page.url();
        expect(currentUrl).toContain(sessionId!);
    });

    test('refresh preserves session', async ({ page }) => {
        // Navigate to a session
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        const urlBefore = page.url();

        // Refresh
        await page.reload();
        await page.waitForLoadState('networkidle');

        // Same session
        const urlAfter = page.url();
        expect(urlAfter).toBe(urlBefore);
    });

    test('new session gets unique URL', async ({ page }) => {
        // First session
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        const url1 = page.url();

        // Navigate to new session
        const newId = crypto.randomUUID();
        await page.goto(`/chat/${newId}`);
        await page.waitForLoadState('networkidle');

        const url2 = page.url();
        expect(url2).toContain(newId);
        expect(url2).not.toBe(url1);
    });
});

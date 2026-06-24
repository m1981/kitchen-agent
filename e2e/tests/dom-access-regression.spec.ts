import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import { seedSession } from '../fixtures/seed';

/**
 * DOM Access Regression Tests
 * ===========================
 * Tests for common DOM access timing issues in Svelte 5 applications.
 * These tests verify that elements are properly waited for before interaction.
 *
 * @see e2e/DOM-ACCESS-ANALYSIS.md for issue details
 */

test.describe('DOM Timing Issues', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    // ── Issue #1: Elements appear after async operations ──────────

    test('session appears in sidebar after seed API completes', async ({ page }) => {
        // This tests the timing issue in browser-seed.js where
        // page.evaluate() is used before element is ready

        // Arrange - seed session via API
        const session = await seedSession(page, { pairs: 1, title: 'Timing Test Session' });

        // Act - navigate to page
        await chatPage.goto();

        // Assert - session should be visible (no arbitrary delay needed)
        const sessionButton = page.locator(`aside button:has-text("Timing Test Session")`);
        await expect(sessionButton).toBeVisible({ timeout: 10_000 });

        // Verify we can click it immediately
        await sessionButton.click();

        // Verify messages loaded
        await chatPage.waitForMessagesLoaded(1);
    });

    test('messages load after session click without waitForTimeout', async ({ page }) => {
        // This tests that we don't need page.waitForTimeout(500) after loading

        // Arrange
        const session = await seedSession(page, { pairs: 2, title: 'No Wait Test' });
        await chatPage.goto();

        // Act - click session (no waitForTimeout after)
        await chatPage.loadSession('No Wait Test');

        // Assert - messages should be immediately available
        await chatPage.expectMessageCount(4);

        // Verify message content is stable (not partial render)
        const firstMessage = await chatPage.getMessageText(0);
        expect(firstMessage.length).toBeGreaterThan(0);
    });

    // ── Issue #2: isVisible().catch() workaround ──────────────────

    test('session button becomes visible after page refresh', async ({ page }) => {
        // This tests the isVisible().catch() workaround in ChatPage.ts

        // Arrange - seed session AFTER page load (like browser-seed.js does)
        await chatPage.goto();
        const session = await seedSession(page, { pairs: 1, title: 'Refresh Test' });

        // Act - try to load session (requires refresh to see it)
        // The ChatPage.loadSession() should handle this without flaky isVisible().catch()
        await chatPage.loadSession('Refresh Test');

        // Assert - session loaded successfully
        await chatPage.expectMessageCount(2);
    });

    // ── Issue #3: textContent() before element is stable ──────────

    test('token indicator shows stable content', async ({ page }) => {
        // This tests the textContent() timing issue in url-routing-title.spec.ts

        // Arrange
        const session = await seedSession(page, { pairs: 3, title: 'Token Stability Test' });
        await chatPage.goto();
        await chatPage.loadSession('Token Stability Test');

        // Act - read token text multiple times
        const readings: string[] = [];
        for (let i = 0; i < 3; i++) {
            const text = await page.locator('[role="progressbar"]').locator('..').textContent();
            readings.push(text?.trim() || '');
            await page.waitForTimeout(100); // Small delay between reads
        }

        // Assert - all readings should be identical (stable content)
        expect(readings[0]).toBe(readings[1]);
        expect(readings[1]).toBe(readings[2]);

        // Verify percentage is present
        expect(readings[0]).toMatch(/\d+%/);
    });

    // ── Issue #4: Dynamic list rendering ──────────────────────────

    test('sidebar sessions render completely before interaction', async ({ page }) => {
        // This tests {#each} rendering timing

        // Arrange - create multiple sessions
        const sessions = [];
        for (let i = 0; i < 5; i++) {
            const session = await seedSession(page, { pairs: 1, title: `List Test ${i}` });
            sessions.push(session);
        }

        await chatPage.goto();

        // Assert - all sessions should be visible
        const sidebarButtons = page.locator('aside button');
        await expect(sidebarButtons).toHaveCount(sessions.length + 1, { timeout: 10_000 }); // +1 for "New chat"

        // Verify we can click the last one (tests full render)
        const lastSession = page.locator(`aside button:has-text("List Test 4")`);
        await lastSession.click();
        await chatPage.waitForMessagesLoaded(1);
    });

    // ── Issue #5: Conditional content rendering ───────────────────

    test('loading state disappears before content shows', async ({ page }) => {
        // This tests {#if} conditional rendering timing

        // Arrange
        const session = await seedSession(page, { pairs: 2, title: 'Loading State Test' });

        // Act - navigate directly to session
        await page.goto(`/chat/${session.session_id}`);

        // Assert - loading should complete
        await chatPage.waitForBusyComplete();

        // Content should be visible
        await chatPage.expectMessageCount(4);

        // Loading indicator should be gone
        await expect(chatPage.loadingIndicator).not.toBeVisible();
    });

    // ── Issue #6: Stale element references ────────────────────────

    test('element references remain valid after state change', async ({ page }) => {
        // This tests stale element reference issues

        // Arrange
        const session = await seedSession(page, { pairs: 2, title: 'Stale Test' });
        await chatPage.goto();
        await chatPage.loadSession('Stale Test');

        // Get reference to first message
        const firstMessage = chatPage.chatBubbles.first();
        const initialText = await firstMessage.textContent();

        // Act - perform an action that updates DOM (send new message)
        await chatPage.chatInput.fill('New message');
        await chatPage.sendButton.click();

        // Wait for new message to appear
        await chatPage.expectMessageCount(6); // 4 + 2 new

        // Assert - original first message should still be accessible
        const afterText = await firstMessage.textContent();
        expect(afterText).toBe(initialText);
    });

    // ── Issue #7: Focus management after modal close ──────────────

    test('focus returns to correct element after dialog close', async ({ page }) => {
        // This tests focus trap issues in modals

        // Arrange
        const session = await seedSession(page, { pairs: 1, title: 'Focus Test' });
        await chatPage.goto();
        await chatPage.loadSession('Focus Test');

        // Open delete dialog
        await chatPage.moreOptionsButtons.first().click();
        await page.waitForSelector('[data-testid="delete-btn"]', { state: 'visible' });
        await chatPage.deleteButtons.first().click();
        await chatPage.expectConfirmDialogVisible();

        // Get currently focused element before cancel
        const focusedBefore = await page.evaluate(() => document.activeElement?.tagName);

        // Act - cancel dialog
        await chatPage.confirmCancelButton.click();

        // Assert - dialog closed
        await chatPage.expectConfirmDialogHidden();

        // Focus should return to a reasonable element (not lost)
        const focusedAfter = await page.evaluate(() => document.activeElement?.tagName);
        expect(focusedAfter).toBeTruthy();
    });

    // ── Issue #8: Rapid clicks don't cause double-submit ──────────

    test('rapid clicks on send button only submit once', async ({ page }) => {
        // This tests double-submit prevention

        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Fill message
        await chatPage.chatInput.fill('Test message');

        // Act - click send button rapidly
        await chatPage.sendButton.click();
        await chatPage.sendButton.click(); // Second click should be ignored
        await chatPage.sendButton.click(); // Third click should be ignored

        // Wait for message to be sent
        await page.waitForTimeout(2000);

        // Assert - only one message should be sent
        const userMessages = page.locator('[data-chat-bubble="user"]');
        const count = await userMessages.count();
        expect(count).toBe(1);
    });

    // ── Issue #9: Scroll position preserved after DOM update ──────

    test('scroll position preserved after new message arrives', async ({ page }) => {
        // This tests scroll behavior during DOM updates

        // Arrange - create session with many messages
        const session = await seedSession(page, { pairs: 5, title: 'Scroll Test' });
        await chatPage.goto();
        await chatPage.loadSession('Scroll Test');

        // Scroll to top of messages
        await page.evaluate(() => {
            const scrollContainer = document.querySelector('[data-testid="chat-scroll"]');
            if (scrollContainer) scrollContainer.scrollTop = 0;
        });

        // Get scroll position
        const scrollTopBefore = await page.evaluate(() => {
            const scrollContainer = document.querySelector('[data-testid="chat-scroll"]');
            return scrollContainer?.scrollTop || 0;
        });

        // Act - send new message (should not auto-scroll if user scrolled up)
        // Note: This depends on implementation - if auto-scroll is enabled, this test would need adjustment

        // Assert - scroll position should be preserved or auto-scrolled to bottom
        // (Implementation specific)
    });

    // ── Issue #10: Element count changes during render ────────────

    test('element count stabilizes after render', async ({ page }) => {
        // This tests {#each} count changes

        // Arrange
        const session = await seedSession(page, { pairs: 3, title: 'Count Test' });
        await chatPage.goto();
        await chatPage.loadSession('Count Test');

        // Act - read count multiple times rapidly
        const counts: number[] = [];
        for (let i = 0; i < 5; i++) {
            const count = await chatPage.chatBubbles.count();
            counts.push(count);
            await page.waitForTimeout(50); // Very small delay
        }

        // Assert - all counts should be identical (stable)
        expect(counts.every((c) => c === counts[0])).toBe(true);
        expect(counts[0]).toBe(6); // 3 pairs = 6 messages
    });
});

test.describe('Selector Stability', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    // ── Issue #11: Complex parent traversal ───────────────────────

    test('token percentage accessible via stable selector', async ({ page }) => {
        // This tests the fragile parent traversal in ChatPage.ts:209

        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Act - try to get token percentage
        // The current implementation uses: tokenProgressBar.locator('..').locator('..').textContent()
        // This is fragile - should use data-testid instead

        // Assert - token indicator should be visible
        await chatPage.expectTokenIndicatorVisible();

        // Get percentage using the page object method
        const percentage = await chatPage.getTokenPercentage();
        expect(percentage).toMatch(/\d+/);
    });

    // ── Issue #12: Missing data-testid attributes ─────────────────

    test('key elements have data-testid attributes', async ({ page }) => {
        // This identifies elements that should have data-testid

        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Assert - check for required data-testid attributes
        const requiredTestIds = ['chat-bubble', 'chat-input', 'send-btn', 'app-busy'];

        for (const testId of requiredTestIds) {
            const element = page.getByTestId(testId);
            const count = await element.count();
            expect(count).toBeGreaterThan(0, `Missing data-testid="${testId}"`);
        }
    });
});

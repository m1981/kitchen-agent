/**
 * Seeded Session Screenshots
 * ==========================
 * Screenshots with real session data (not empty).
 *
 * Run: npx playwright test e2e/visual/components/seeded-screenshots.spec.ts
 * Output: e2e/test-results/screenshots/
 */

import { test } from '@playwright/test';
import { seedSession, deleteSession } from '../../fixtures/seed';
import { screenshot } from '../../fixtures/screenshots';

test.describe('Seeded Session Screenshots', () => {
    let sessionId: string;

    test.afterEach(async ({ page }) => {
        // Cleanup
        if (sessionId) {
            await deleteSession(page, sessionId).catch(() => {});
        }
    });

    test('desktop with conversation', async ({ page }) => {
        // Seed a session with 3 message pairs
        const session = await seedSession(page, {
            pairs: 3,
            title: 'Kitchen Layout Discussion'
        });
        sessionId = session.session_id;

        // Navigate to the session
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto(`/chat/${sessionId}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);

        // → desktop-seeded-conversation.png
        await screenshot(page, 'seeded-conversation', { viewport: 'desktop' });
    });

    test('desktop with sidebar and sessions', async ({ page }) => {
        // Seed multiple sessions
        const session1 = await seedSession(page, { pairs: 2, title: 'Material Selection' });
        const session2 = await seedSession(page, { pairs: 1, title: 'Assembly Instructions' });
        sessionId = session1.session_id;

        // Navigate to first session
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto(`/chat/${sessionId}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);

        // Open sidebar
        const toggle = page.locator('[data-testid="sidebar-toggle"]');
        if (await toggle.isVisible()) {
            await toggle.click();
            await page.waitForTimeout(300);
        }

        // → desktop-seeded-sidebar-sessions.png
        await screenshot(page, 'seeded-sidebar-sessions', { viewport: 'desktop' });

        // Cleanup extra sessions
        await deleteSession(page, session2.session_id).catch(() => {});
    });

    test('mobile with conversation', async ({ page }) => {
        // Seed a session with 2 message pairs
        const session = await seedSession(page, {
            pairs: 2,
            title: 'Mobile Chat View'
        });
        sessionId = session.session_id;

        // Navigate to the session
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto(`/chat/${sessionId}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);

        // → mobile-seeded-conversation.png
        await screenshot(page, 'seeded-conversation', { viewport: 'mobile' });
    });

    test('desktop with system prompt', async ({ page }) => {
        // Seed a session
        const session = await seedSession(page, {
            pairs: 2,
            title: 'System Prompt Test'
        });
        sessionId = session.session_id;

        // Navigate to the session
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto(`/chat/${sessionId}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);

        // Expand system prompt
        const systemPrompt = page.locator('[aria-label="System prompt"] button').first();
        if (await systemPrompt.isVisible()) {
            await systemPrompt.click();
            await page.waitForTimeout(300);
        }

        // → desktop-seeded-system-prompt.png
        await screenshot(page, 'seeded-system-prompt', { viewport: 'desktop' });
    });

    test('desktop with context files', async ({ page }) => {
        // Seed a session
        const session = await seedSession(page, {
            pairs: 2,
            title: 'Context Files View'
        });
        sessionId = session.session_id;

        // Navigate to the session
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto(`/chat/${sessionId}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);

        // Click "Hide panel" to show context panel
        const hidePanel = page.locator('button:has-text("Hide panel")');
        if (await hidePanel.isVisible()) {
            await hidePanel.click();
            await page.waitForTimeout(300);
        }

        // → desktop-seeded-context-panel.png
        await screenshot(page, 'seeded-context-panel', { viewport: 'desktop' });
    });
});

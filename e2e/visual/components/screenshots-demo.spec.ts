/**
 * Screenshot Demo
 * ===============
 * Shows how to use auto-named screenshots.
 *
 * Run: npx playwright test e2e/visual/components/screenshots-demo.spec.ts
 * Output: e2e/test-results/screenshots/
 */

import { test } from '@playwright/test';
import { screenshot } from '../../fixtures/screenshots';

test.describe('Auto-named Screenshots', () => {
    test('desktop layout', async ({ page }) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // → desktop-home-full.png
        await screenshot(page, 'home-full', { viewport: 'desktop' });

        // Open sidebar
        const toggle = page.locator('[data-testid="sidebar-toggle"]');
        if (await toggle.isVisible()) {
            await toggle.click();
            await page.waitForTimeout(300);
        }

        // → desktop-home-sidebar.png
        await screenshot(page, 'home-sidebar', { viewport: 'desktop' });
    });

    test('mobile layout', async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // → mobile-home-full.png
        await screenshot(page, 'home-full', { viewport: 'mobile' });

        // Open model selector
        const selector = page.locator('[aria-label="Select model"]');
        if (await selector.isVisible()) {
            await selector.click();
            await page.waitForTimeout(500);
        }

        // → mobile-home-model-selector.png
        await screenshot(page, 'home-model-selector', { viewport: 'mobile' });
    });

    test('composer states', async ({ page }) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // → desktop-composer-empty.png
        await screenshot(page, 'composer-empty', { viewport: 'desktop' });

        // Type a message
        const input = page.locator('[data-testid="chat-input"]');
        await input.fill('Hello, this is a test message');

        // → desktop-composer-with-text.png
        await screenshot(page, 'composer-with-text', { viewport: 'desktop' });
    });

    test('system prompt states', async ({ page }) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // → desktop-system-prompt-collapsed.png
        await screenshot(page, 'system-prompt-collapsed', { viewport: 'desktop' });

        // Expand
        const toggle = page.locator('[aria-label="System prompt"] button').first();
        if (await toggle.isVisible()) {
            await toggle.click();
            await page.waitForTimeout(300);
        }

        // → desktop-system-prompt-expanded.png
        await screenshot(page, 'system-prompt-expanded', { viewport: 'desktop' });
    });
});

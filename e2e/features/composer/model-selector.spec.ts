import { test, expect } from '@playwright/test';
import { ComposerPage } from '../../page-objects/ComposerPage';

test.describe('Model Selector @regression', () => {
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('model selector dropdown is visible', async () => {
        await expect(composerPage.modelSelector).toBeVisible();
    });

    test('model selector has options', async () => {
        const options = await composerPage.modelSelector.locator('option').count();
        expect(options).toBeGreaterThan(0);
    });

    test('model selector shows provider groups', async () => {
        const optgroups = await composerPage.modelSelector.locator('optgroup').count();
        expect(optgroups).toBeGreaterThan(0);
    });

    test('default model is selected', async () => {
        const value = await composerPage.getSelectedModel();
        expect(value).toBeTruthy();
    });
});

test.describe('Tools Toggle @regression', () => {
    let composerPage: ComposerPage;

    test.beforeEach(async ({ page }) => {
        composerPage = new ComposerPage(page);

        await page.goto('/');
        await page.waitForLoadState('networkidle');
    });

    test('tools toggle visible', async () => {
        await expect(composerPage.toolsToggle).toBeVisible();
    });

    test('tools enabled by default', async () => {
        await composerPage.expectToolsState(true);
    });

    test('click toggles tools off', async () => {
        await composerPage.toggleTools();
        await composerPage.expectToolsState(false);
    });

    test('click toggles tools back on', async () => {
        await composerPage.toggleTools();
        await composerPage.toggleTools();
        await composerPage.expectToolsState(true);
    });

    test('tools state persists after page reload', async ({ page }) => {
        // Toggle off
        await composerPage.toggleTools();
        await composerPage.expectToolsState(false);

        // Reload
        await page.reload();
        await page.waitForLoadState('networkidle');

        // Should still be off
        await composerPage.expectToolsState(false);
    });
});

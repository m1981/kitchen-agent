import { Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Auto-named screenshot utility.
 *
 * Screenshots saved to: e2e/test-results/screenshots/
 * Filename format: {viewport}-{label}.png
 *
 * Usage:
 *   import { screenshot } from '../fixtures/screenshots';
 *   await screenshot(page, 'home-full', { viewport: 'desktop' });
 */

const SCREENSHOT_DIR = path.resolve(__dirname, '../test-results/screenshots');

if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

export interface ScreenshotOptions {
    viewport?: string;
    fullPage?: boolean;
}

/**
 * Take an auto-named screenshot
 */
export async function screenshot(
    page: Page,
    label: string,
    options?: ScreenshotOptions
): Promise<string> {
    const viewport = options?.viewport || 'desktop';
    const filename = `${viewport}-${label}.png`;
    const filepath = path.join(SCREENSHOT_DIR, filename);

    await page.screenshot({
        path: filepath,
        fullPage: options?.fullPage || false
    });

    return filepath;
}

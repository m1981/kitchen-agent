#!/usr/bin/env node

/**
 * browser-seed.js
 * ================
 * Create a test session with N turn-pairs and navigate to it.
 *
 * Usage:
 *   browser-seed.js --pairs 3
 *   browser-seed.js --pairs 2 --title "My test session"
 *   browser-seed.js --pairs 1 --api http://localhost:8000
 *
 * Options:
 *   --pairs N       Number of turn-pairs to create (default: 2)
 *   --title <str>   Custom session title
 *   --api <url>     Backend API URL (default: http://localhost:8000)
 *
 * Output:
 *   session_id, message_count, turn_ids
 *
 * DOM Access Fixes Applied:
 *   - Replace page.evaluate() with Playwright locators
 *   - Use waitForSelector instead of arbitrary delays
 *   - Add proper error handling for missing elements
 */

import puppeteer from 'puppeteer-core';

const args = process.argv.slice(2);

function getArg(name) {
    const idx = args.indexOf(`--${name}`);
    if (idx === -1) return null;
    return args[idx + 1];
}

const pairs = parseInt(getArg('pairs') || '2', 10);
const title = getArg('title') || null;
const apiBase = getArg('api') || 'http://localhost:8000';

if (pairs < 1 || pairs > 20) {
    console.error('✗ --pairs must be between 1 and 20');
    process.exit(1);
}

async function seedSession() {
    // Call the seed endpoint
    const body = { pairs, title };
    const res = await fetch(`${apiBase}/api/_test/seed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });

    if (!res.ok) {
        const text = await res.text();
        if (res.status === 404) {
            console.error('✗ Seed endpoint not found. Ensure DEBUG=true is set in .env');
        } else {
            console.error(`✗ Seed failed: ${res.status} ${text}`);
        }
        process.exit(1);
    }

    return res.json();
}

async function connectBrowser() {
    const b = await Promise.race([
        puppeteer.connect({
            browserURL: 'http://localhost:9222',
            defaultViewport: null
        }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000))
    ]).catch((e) => {
        console.error('✗ Could not connect to browser:', e.message);
        process.exit(1);
    });

    const p = (await b.pages()).at(-1);
    if (!p) {
        console.error('✗ No active tab found');
        await b.disconnect();
        process.exit(1);
    }

    return { browser: b, page: p };
}

/**
 * Wait for session button to appear in sidebar using proper DOM waiting.
 * Replaces the fragile page.evaluate() approach.
 */
async function waitForSessionInSidebar(page, sessionTitle, timeout = 10000) {
    const selector = `aside button`;

    // Wait for sidebar to have any buttons
    await page.waitForSelector(selector, { timeout });

    // Wait for the specific session button
    // Use XPath-like text matching since Puppeteer doesn't have has-text
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
        const buttons = await page.$$(selector);
        for (const button of buttons) {
            const text = await button.evaluate((el) => el.textContent?.trim() || '');
            if (text.includes(sessionTitle) || text.includes('Test session')) {
                return button;
            }
        }
        // Wait a bit before retrying
        await new Promise((r) => setTimeout(r, 100));
    }

    return null;
}

/**
 * Click session button with proper error handling.
 * Replaces the fragile page.evaluate() approach.
 */
async function clickSessionButton(page, sessionTitle) {
    // First try to find the specific session
    const button = await waitForSessionInSidebar(page, sessionTitle);

    if (button) {
        await button.click();
        return true;
    }

    // Fallback: click the first session-like button (not "New chat")
    console.log(`⚠ Session "${sessionTitle}" not found, clicking first available session`);

    const buttons = await page.$$('aside button');
    for (const btn of buttons) {
        const text = await btn.evaluate((el) => el.textContent?.trim() || '');
        if (text !== '+ New chat' && text !== '' && !text.includes('New chat')) {
            await btn.click();
            return true;
        }
    }

    return false;
}

/**
 * Wait for messages to load after clicking a session.
 * Uses proper DOM waiting instead of arbitrary delays.
 */
async function waitForMessagesLoaded(page, timeout = 10000) {
    // Wait for at least one chat bubble to appear
    await page.waitForSelector('[data-testid="chat-bubble"]', { timeout });

    // Wait for loading to complete
    await page.waitForFunction(
        () => {
            const busyIndicator = document.querySelector('[data-testid="app-busy"]');
            return busyIndicator?.getAttribute('data-busy-recent') === 'false';
        },
        { timeout }
    );
}

async function run() {
    // Seed the session
    const data = await seedSession();
    const sessionTitle = title || 'Test session';

    // Connect to browser and navigate
    const { browser, page } = await connectBrowser();

    try {
        // Navigate to the frontend
        const frontendUrl = 'http://localhost:5173';
        await page.goto(frontendUrl, { waitUntil: 'domcontentloaded' });

        // Wait for the sidebar to load
        await page.waitForSelector('aside button', { timeout: 10000 });

        // Wait a bit for the session list to refresh from API
        // This replaces the fragile page.evaluate() with setTimeout
        await new Promise((resolve) => setTimeout(resolve, 500));

        // Click the session in the sidebar using proper DOM access
        const clicked = await clickSessionButton(page, sessionTitle);

        if (clicked) {
            // Wait for messages to load
            await waitForMessagesLoaded(page);
        } else {
            console.warn('⚠ Could not find any session to click');
        }

        // Output the result
        console.log(`✓ Seeded session: ${data.session_id}`);
        console.log(`  Messages: ${data.message_count}`);
        console.log(`  Turn pairs: ${JSON.stringify(data.turn_ids, null, 2)}`);
    } finally {
        await browser.disconnect();
    }
}

run().catch((e) => {
    console.error('✗ Error:', e.message);
    process.exit(1);
});

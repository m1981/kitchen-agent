import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';
import path from 'path';

/**
 * Playwright E2E Test Configuration
 *
 * Uses isolated ports (5174/8001) to avoid conflicts with dev servers.
 * Playwright manages server lifecycle automatically.
 *
 * @see https://playwright.dev/docs/test-configuration
 */

// Load .env file for E2E-specific settings
dotenv.config({ path: path.resolve(__dirname, '.env.e2e') });

const E2E_BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8001';
const E2E_FRONTEND_PORT = process.env.E2E_FRONTEND_PORT || '5174';
const E2E_DATA_DIR = process.env.E2E_DATA_DIR || 'data-e2e';

export default defineConfig({
    testDir: './e2e',
    testMatch: ['**/*.spec.ts', '**/tests/**/*.spec.ts'],

    /* Run tests in files in parallel */
    fullyParallel: true,

    /* Fail the build on CI if you accidentally left test.only in the source code */
    forbidOnly: !!process.env.CI,

    /* Retry on CI only */
    retries: process.env.CI ? 2 : 0,

    /* Opt out of parallel tests - ensures test isolation with shared database */
    workers: 1,

    /* Reporter to use */
    reporter: [
        ['html', { outputFolder: 'e2e/test-results/html' }],
        ['json', { outputFile: 'e2e/test-results/results.json' }],
        ['list']
    ],

    /* Shared settings for all the projects below */
    use: {
        /* Base URL to use in actions like `await page.goto('/')` */
        baseURL: `http://localhost:${E2E_FRONTEND_PORT}`,

        /* Collect trace when retrying the failed test */
        trace: 'on-first-retry',

        /* Screenshot on failure */
        screenshot: 'only-on-failure',

        /* Video on failure */
        video: 'retain-on-failure',

        /* Default timeout for actions */
        actionTimeout: 10_000,

        /* Default timeout for navigation */
        navigationTimeout: 30_000
    },

    /* Configure projects for major browsers */
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] }
        }
    ],

    /* Run your local dev server before starting the tests */
    webServer: [
        {
            command: `cd . && source .venv/bin/activate && DEBUG=true E2E_TEST=true DATA_DIR=${E2E_DATA_DIR} python -m uvicorn src.main:app --port ${E2E_BACKEND_PORT}`,
            port: parseInt(E2E_BACKEND_PORT),
            timeout: 120_000,
            reuseExistingServer: false,
            env: {
                DEBUG: 'true',
                E2E_TEST: 'true',
                DATA_DIR: E2E_DATA_DIR
            }
        },
        {
            command: `cd frontend && npm run dev -- --port ${E2E_FRONTEND_PORT}`,
            port: parseInt(E2E_FRONTEND_PORT),
            timeout: 120_000,
            reuseExistingServer: false,
            env: {
                VITE_API_BASE: `http://localhost:${E2E_BACKEND_PORT}`
            }
        }
    ]
});

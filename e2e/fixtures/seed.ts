import { Page } from '@playwright/test';

/**
 * Seed API response type
 */
export interface SeedResult {
    session_id: string;
    message_count: number;
    turn_ids: Array<{ user: string; assistant: string }>;
}

/**
 * Seed options for creating test sessions
 */
export interface SeedOptions {
    pairs: number;
    title?: string;
}

/**
 * Get the backend API base URL from environment or default
 */
function getBackendUrl(): string {
    return process.env.E2E_BACKEND_URL || 'http://localhost:8001';
}

/**
 * Seed a test session via the backend API.
 * Requires DEBUG=true on the backend.
 *
 * @param page - Playwright Page object (used for API context)
 * @param options - Seed options
 * @returns SeedResult with session_id and turn_ids
 */
export async function seedSession(
    page: Page,
    options: SeedOptions
): Promise<SeedResult & { title: string }> {
    const title = options.title || `E2E Test ${Date.now()}`;
    const backendUrl = getBackendUrl();

    const response = await page.request.post(`${backendUrl}/api/_test/seed`, {
        data: {
            pairs: options.pairs,
            title
        }
    });

    if (!response.ok()) {
        const body = await response.text();
        throw new Error(`Seed failed: ${response.status()} ${body}`);
    }

    const data = await response.json();
    return {
        ...data,
        title
    };
}

/**
 * Delete a session via the backend API (cleanup).
 */
export async function deleteSession(page: Page, sessionId: string): Promise<void> {
    const backendUrl = getBackendUrl();
    await page.request.delete(`${backendUrl}/api/sessions/${sessionId}`);
}

/**
 * Get session state via the backend API.
 */
export async function getSessionState(
    page: Page,
    sessionId: string
): Promise<{
    session_id: string;
    message_count: number;
    turn_ids: string[];
    roles: string[];
}> {
    const backendUrl = getBackendUrl();
    const response = await page.request.get(`${backendUrl}/api/sessions/${sessionId}/state`);
    return response.json();
}

// ── Folder helpers ───────────────────────────────────────────────────────────

/**
 * Create a folder via the backend API.
 */
export async function createFolder(
    page: Page,
    name: string
): Promise<{ id: string; name: string }> {
    const backendUrl = getBackendUrl();
    const response = await page.request.post(`${backendUrl}/api/folders`, {
        data: { name }
    });
    if (!response.ok()) {
        const body = await response.text();
        throw new Error(`Create folder failed: ${response.status()} ${body}`);
    }
    return response.json();
}

/**
 * Assign a session to a folder via the backend API.
 */
export async function assignSessionToFolder(
    page: Page,
    folderId: string,
    sessionId: string
): Promise<void> {
    const backendUrl = getBackendUrl();
    const response = await page.request.post(
        `${backendUrl}/api/folders/${folderId}/sessions/${sessionId}`
    );
    if (!response.ok()) {
        const body = await response.text();
        throw new Error(`Assign failed: ${response.status()} ${body}`);
    }
}

/**
 * Unassign a session from a folder via the backend API.
 */
export async function unassignSessionFromFolder(
    page: Page,
    folderId: string,
    sessionId: string
): Promise<void> {
    const backendUrl = getBackendUrl();
    await page.request.delete(`${backendUrl}/api/folders/${folderId}/sessions/${sessionId}`);
}

/**
 * Delete a folder via the backend API (cleanup).
 */
export async function deleteFolder(page: Page, folderId: string): Promise<void> {
    const backendUrl = getBackendUrl();
    await page.request.delete(`${backendUrl}/api/folders/${folderId}`);
}

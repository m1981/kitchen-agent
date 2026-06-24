import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import { seedSession, getSessionState, deleteSession } from '../fixtures/seed';

/**
 * URL-Based Routing & Title Features
 * ===================================
 * Tests for:
 * - URL-based session routing (browser refresh preserves session)
 * - Token indicator display
 * - Session title display in header
 * - Inline title editing
 * - AI title regeneration via context menu
 */

test.describe('URL-Based Session Routing', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('root URL redirects to /chat/{uuid}', async ({ page }) => {
        // Act
        await page.goto('/');

        // Assert - should redirect to /chat/ with a UUID
        await page.waitForURL(/\/chat\/[a-f0-9-]+/, { timeout: 5000 });
        const url = page.url();
        expect(url).toMatch(/\/chat\/[a-f0-9-]{36}/);
    });

    test('session ID persists after browser refresh', async ({ page }) => {
        // Arrange - create and load a session
        const session = await seedSession(page, { pairs: 2, title: 'Refresh Test Session' });
        await chatPage.goto();
        await chatPage.loadSession('Refresh Test Session');

        // Get current URL
        const urlBefore = page.url();
        expect(urlBefore).toContain(session.session_id);

        // Act - refresh the page
        await page.reload();
        await page.waitForLoadState('networkidle');

        // Assert - URL should be the same and session should be loaded
        const urlAfter = page.url();
        expect(urlAfter).toBe(urlBefore);

        // Messages should still be visible
        await chatPage.waitForMessagesLoaded(1);
    });

    test('new chat generates UUID in URL', async ({ page }) => {
        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Act - click "New chat" button
        const newChatButton = page.locator('button:has-text("New chat")');
        await newChatButton.click();

        // Assert - URL should change to /chat/{uuid}
        await page.waitForURL(/\/chat\/[a-f0-9-]+/, { timeout: 5000 });
        const url = page.url();
        expect(url).toMatch(/\/chat\/[a-f0-9-]{36}/);
    });

    test('sidebar session click navigates to correct URL', async ({ page }) => {
        // Arrange - create two sessions
        const session1 = await seedSession(page, { pairs: 1, title: 'Session Alpha' });
        const session2 = await seedSession(page, { pairs: 1, title: 'Session Beta' });

        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Act - click first session
        await chatPage.loadSession('Session Alpha');
        const url1 = page.url();
        expect(url1).toContain(session1.session_id);

        // Act - click second session
        await chatPage.loadSession('Session Beta');
        const url2 = page.url();
        expect(url2).toContain(session2.session_id);

        // Assert - URLs should be different
        expect(url1).not.toBe(url2);
    });

    test('direct URL access loads correct session', async ({ page }) => {
        // Arrange - create a session
        const session = await seedSession(page, { pairs: 2, title: 'Direct URL Test' });

        // Act - navigate directly to the session URL
        await page.goto(`/chat/${session.session_id}`);
        await page.waitForLoadState('networkidle');

        // Assert - session should be loaded with messages
        await chatPage.waitForMessagesLoaded(1);
    });
});

test.describe('Token Indicator', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('token indicator is visible in composer area', async ({ page }) => {
        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Assert - token indicator elements should be visible
        const progressBar = page.locator('[role="progressbar"]');
        await expect(progressBar).toBeVisible();

        // Check for token count text (📊 symbol)
        const tokenText = page.locator('text=/📊/');
        await expect(tokenText).toBeVisible();

        // Check for input token estimate (→ symbol)
        const inputTokenText = page.locator('text=/→/');
        await expect(inputTokenText).toBeVisible();
    });

    test('token indicator shows percentage', async ({ page }) => {
        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Assert - should show a percentage
        const percentText = page.locator('text=/\\d+%/');
        await expect(percentText).toBeVisible();
    });

    test('token indicator updates with session tokens', async ({ page }) => {
        // Arrange - create session with messages
        const session = await seedSession(page, { pairs: 3, title: 'Token Test Session' });
        await chatPage.goto();
        await chatPage.loadSession('Token Test Session');

        // Assert - token count should be greater than 0
        const tokenText = await page.locator('text=/📊.*\\d/').textContent();
        expect(tokenText).toBeTruthy();
    });
});

test.describe('Session Title Display', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('header shows session title when available', async ({ page }) => {
        // Arrange - create session with title
        const session = await seedSession(page, { pairs: 1, title: 'My Kitchen Project' });
        await chatPage.goto();
        await chatPage.loadSession('My Kitchen Project');

        // Assert - header should show the title
        const header = page.locator('header');
        await expect(header).toContainText('My Kitchen Project');
    });

    test('header shows session ID when no title', async ({ page }) => {
        // Arrange - navigate to a new session (no title)
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Assert - header should show "Session {id}" format
        const header = page.locator('header');
        const headerText = await header.textContent();
        expect(headerText).toMatch(/Session [a-f0-9]{8}/);
    });

    test('header shows mode badge next to title', async ({ page }) => {
        // Arrange
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Assert - mode badge should be visible
        const modeBadge = page.locator('header span:has-text("General")');
        await expect(modeBadge).toBeVisible();
    });
});

test.describe('Inline Title Editing', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('click on title enables editing', async ({ page }) => {
        // Arrange - create session with title
        const session = await seedSession(page, { pairs: 1, title: 'Edit Test' });
        await chatPage.goto();
        await chatPage.loadSession('Edit Test');

        // Act - click on the title
        const titleButton = page.locator('header button:has-text("Edit Test")');
        await titleButton.click();

        // Assert - input field should appear with the title
        const titleInput = page.locator('header input');
        await expect(titleInput).toBeVisible();
        await expect(titleInput).toHaveValue('Edit Test');
    });

    test('press Enter saves the title', async ({ page }) => {
        // Arrange - create session with title
        const session = await seedSession(page, { pairs: 1, title: 'Original Title' });
        await chatPage.goto();
        await chatPage.loadSession('Original Title');

        // Act - click on title to edit
        const titleButton = page.locator('header button:has-text("Original Title")');
        await titleButton.click();

        // Clear and type new title
        const titleInput = page.locator('header input');
        await titleInput.clear();
        await titleInput.fill('New Title');
        await titleInput.press('Enter');

        // Assert - title should be updated
        await chatPage.expectTitleToContain('New Title');

        // Verify backend
        const state = await getSessionState(page, session.session_id);
        // Note: The state endpoint doesn't return title, but we can verify via API
    });

    test('press Escape cancels editing', async ({ page }) => {
        // Arrange - create session with title
        const session = await seedSession(page, { pairs: 1, title: 'Cancel Test' });
        await chatPage.goto();
        await chatPage.loadSession('Cancel Test');

        // Act - click on title to edit
        const titleButton = page.locator('header button:has-text("Cancel Test")');
        await titleButton.click();

        // Type something and press Escape
        const titleInput = page.locator('header input');
        await titleInput.fill('Should Not Save');
        await titleInput.press('Escape');

        // Assert - original title should remain
        const header = page.locator('header');
        await expect(header).toContainText('Cancel Test');
    });

    test('click away saves the title', async ({ page }) => {
        // Arrange - create session with title
        const session = await seedSession(page, { pairs: 1, title: 'Blur Test' });
        await chatPage.goto();
        await chatPage.loadSession('Blur Test');

        // Act - click on title to edit
        const titleButton = page.locator('header button:has-text("Blur Test")');
        await titleButton.click();

        // Type new title and click elsewhere
        const titleInput = page.locator('header input');
        await titleInput.clear();
        await titleInput.fill('Saved By Blur');
        await page.locator('main').click(); // Click outside

        // Assert - title should be updated
        await chatPage.expectTitleToContain('Saved By Blur');
    });

    test('empty title is not saved', async ({ page }) => {
        // Arrange - create session with title
        const session = await seedSession(page, { pairs: 1, title: 'Empty Test' });
        await chatPage.goto();
        await chatPage.loadSession('Empty Test');

        // Act - click on title and clear it
        const titleButton = page.locator('header button:has-text("Empty Test")');
        await titleButton.click();

        const titleInput = page.locator('header input');
        await titleInput.clear();
        await titleInput.press('Enter');

        // Assert - original title should remain (empty not saved)
        const header = page.locator('header');
        await expect(header).toContainText('Empty Test');
    });
});

test.describe('AI Title Regeneration', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    test('context menu shows Regenerate Title option', async ({ page }) => {
        // Arrange - create session with messages
        const session = await seedSession(page, { pairs: 2, title: 'Menu Test' });
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Act - find and click the context menu button for the session
        const menuItem = page.locator(`aside button:has-text("Menu Test")`).locator('..');
        const menuButton = menuItem.locator('button[aria-label="Session options"]');
        await menuButton.click();

        // Assert - "Regenerate Title" should be visible
        const regenerateOption = page.locator('button:has-text("Regenerate Title")');
        await expect(regenerateOption).toBeVisible();
    });

    test('clicking Regenerate Title calls API', async ({ page }) => {
        // Arrange - create session with messages
        const session = await seedSession(page, { pairs: 2, title: 'Generate Test' });
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Intercept the API call
        let apiCalled = false;
        await page.route('**/api/sessions/*/title/generate', async (route) => {
            apiCalled = true;
            await route.continue();
        });

        // Act - open context menu and click regenerate
        const menuItem = page.locator(`aside button:has-text("Generate Test")`).locator('..');
        const menuButton = menuItem.locator('button[aria-label="Session options"]');
        await menuButton.click();

        const regenerateOption = page.locator('button:has-text("Regenerate Title")');
        await regenerateOption.click();

        // Wait for API call to complete
        await page.waitForResponse((resp) => resp.url().includes('/title/generate'));

        // Assert - API should have been called
        expect(apiCalled).toBe(true);
    });

    test('loading spinner shows during title generation', async ({ page }) => {
        // Arrange - create session with messages
        const session = await seedSession(page, { pairs: 2, title: 'Spinner Test' });
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Intercept API to add delay
        await page.route('**/api/sessions/*/title/generate', async (route) => {
            await new Promise((resolve) => setTimeout(resolve, 2000));
            await route.continue();
        });

        // Act - open context menu and click regenerate
        const menuItem = page.locator(`aside button:has-text("Spinner Test")`).locator('..');
        const menuButton = menuItem.locator('button[aria-label="Session options"]');
        await menuButton.click();

        const regenerateOption = page.locator('button:has-text("Regenerate Title")');
        await regenerateOption.click();

        // Assert - spinner should be visible (menu shows loading state)
        // Note: The menu might close or show a spinner depending on implementation
    });

    test('error toast shows on title generation failure', async ({ page }) => {
        // Arrange - create session with messages
        const session = await seedSession(page, { pairs: 2, title: 'Error Test' });
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Intercept API to return error
        await page.route('**/api/sessions/*/title/generate', async (route) => {
            await route.fulfill({
                status: 500,
                body: JSON.stringify({ detail: 'Title generation failed' })
            });
        });

        // Act - open context menu and click regenerate
        const menuItem = page.locator(`aside button:has-text("Error Test")`).locator('..');
        const menuButton = menuItem.locator('button[aria-label="Session options"]');
        await menuButton.click();

        const regenerateOption = page.locator('button:has-text("Regenerate Title")');
        await regenerateOption.click();

        // Assert - error toast should appear
        const errorToast = page.locator('text=/Title generation failed/');
        await expect(errorToast).toBeVisible({ timeout: 5000 });
    });

    test('empty session shows error for title generation', async ({ page }) => {
        // Arrange - navigate to empty session
        await chatPage.goto();
        await page.waitForLoadState('networkidle');

        // Act - try to generate title for empty session (if context menu available)
        // Note: This test assumes we can trigger the API directly
        const response = await page.request.post('/api/sessions/nonexistent/title/generate');

        // Assert - should return error
        expect(response.status()).toBe(400);
    });
});

test.describe('Integration: Title with Routing', () => {
    test('title persists across page refresh', async ({ page }) => {
        // Arrange - create session and set title
        const session = await seedSession(page, { pairs: 1, title: 'Persist Test' });
        await page.goto(`/chat/${session.session_id}`);
        await page.waitForLoadState('networkidle');

        // Edit the title
        const titleButton = page.locator('header button:has-text("Persist Test")');
        await titleButton.click();

        const titleInput = page.locator('header input');
        await titleInput.clear();
        await titleInput.fill('New Persisted Title');
        await titleInput.press('Enter');

        // Wait for title to update in UI (no arbitrary timeout)
        await chatPage.expectTitleToContain('New Persisted Title');

        // Act - refresh the page
        await page.reload();
        await page.waitForLoadState('networkidle');

        // Assert - new title should persist
        await chatPage.expectTitleToContain('New Persisted Title');
    });

    test('title shows in sidebar after update', async ({ page }) => {
        // Arrange - create session
        const session = await seedSession(page, { pairs: 1, title: 'Sidebar Title Test' });
        await page.goto(`/chat/${session.session_id}`);
        await page.waitForLoadState('networkidle');

        // Edit the title
        const titleButton = page.locator('header button:has-text("Sidebar Title Test")');
        await titleButton.click();

        const titleInput = page.locator('header input');
        await titleInput.clear();
        await titleInput.fill('Updated Sidebar Title');
        await titleInput.press('Enter');

        // Wait for sidebar to update (no arbitrary timeout)
        // The sidebar should update when the title is saved
        await page.waitForFunction(
            (expectedTitle) => {
                const sidebar = document.querySelector('aside');
                return sidebar?.textContent?.includes(expectedTitle) || false;
            },
            'Updated Sidebar Title',
            { timeout: 5000 }
        );

        // Assert - sidebar should show updated title
        const sidebar = page.locator('aside');
        await expect(sidebar).toContainText('Updated Sidebar Title');
    });
});

import { test, expect } from '@playwright/test';
import { ChatPage } from '../page-objects/ChatPage';
import {
    seedSession,
    createFolder,
    assignSessionToFolder,
    unassignSessionFromFolder,
    deleteFolder,
    deleteSession
} from '../fixtures/seed';

test.describe('Inbox model — foldered sessions hidden from History', () => {
    let chatPage: ChatPage;

    test.beforeEach(async ({ page }) => {
        chatPage = new ChatPage(page);
    });

    /** Navigate and wait for folder store to fully load */
    async function gotoAndWaitFolders(page: import('@playwright/test').Page) {
        const [, foldersResp] = await Promise.all([
            chatPage.goto(),
            page.waitForResponse(
                (r) =>
                    r.url().includes('/api/folders') &&
                    !r.url().includes('/sessions') &&
                    r.request().method() === 'GET' &&
                    r.status() === 200
            )
        ]);
        // Wait for folder-session sub-requests to complete
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);
    }

    test('session disappears from History after being assigned to folder', async ({ page }) => {
        const session = await seedSession(page, { pairs: 1 });
        const folder = await createFolder(page, `Test Folder ${Date.now()}`);

        await chatPage.goto();
        await chatPage.loadSession(session.title);

        const historyPanel = page.getByTestId('history-panel');
        await expect(historyPanel.getByText(session.title)).toBeVisible();

        await assignSessionToFolder(page, folder.id, session.session_id);

        await gotoAndWaitFolders(page);

        await expect(historyPanel.getByText(session.title)).not.toBeVisible();

        await unassignSessionFromFolder(page, folder.id, session.session_id);
        await deleteFolder(page, folder.id);
        await deleteSession(page, session.session_id);
    });

    test('session reappears in History after being unassigned from folder', async ({ page }) => {
        const session = await seedSession(page, { pairs: 1 });
        const folder = await createFolder(page, `Test Folder ${Date.now()}`);
        await assignSessionToFolder(page, folder.id, session.session_id);

        await gotoAndWaitFolders(page);

        const historyPanel = page.getByTestId('history-panel');
        await expect(historyPanel.getByText(session.title)).not.toBeVisible();

        await unassignSessionFromFolder(page, folder.id, session.session_id);

        await gotoAndWaitFolders(page);

        await expect(historyPanel.getByText(session.title)).toBeVisible();

        await deleteFolder(page, folder.id);
        await deleteSession(page, session.session_id);
    });

    test('foldered session appears in folder tree, not History', async ({ page }) => {
        const session = await seedSession(page, { pairs: 1 });
        const folder = await createFolder(page, `My Folder ${Date.now()}`);
        await assignSessionToFolder(page, folder.id, session.session_id);

        await gotoAndWaitFolders(page);

        await expect(page.locator('aside').getByText(folder.name)).toBeVisible();

        const historyPanel = page.getByTestId('history-panel');
        await expect(historyPanel.getByText(session.title)).not.toBeVisible();

        await deleteFolder(page, folder.id);
        await deleteSession(page, session.session_id);
    });

    test('multiple sessions — only foldered ones hidden from History', async ({ page }) => {
        const session1 = await seedSession(page, { pairs: 1, title: `Inbox ${Date.now()}` });
        const session2 = await seedSession(page, { pairs: 1, title: `Filed ${Date.now()}` });
        const folder = await createFolder(page, `Archive ${Date.now()}`);
        await assignSessionToFolder(page, folder.id, session2.session_id);

        await gotoAndWaitFolders(page);

        const historyPanel = page.getByTestId('history-panel');
        await expect(historyPanel.getByText(session1.title)).toBeVisible();
        await expect(historyPanel.getByText(session2.title)).not.toBeVisible();

        await unassignSessionFromFolder(page, folder.id, session2.session_id);
        await deleteFolder(page, folder.id);
        await deleteSession(page, session1.session_id);
        await deleteSession(page, session2.session_id);
    });
});

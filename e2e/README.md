# E2E Tests

End-to-end tests for Kitchen Agent using Playwright.

## Structure

```
e2e/
├── fixtures/
│   └── seed.ts              # Test data helpers (seed/cleanup sessions)
├── page-objects/
│   └── ChatPage.ts          # Page Object Model for Chat UI
├── tests/
│   ├── message-delete.spec.ts  # Message deletion tests
│   └── truncate.spec.ts        # Message truncation tests
└── README.md
```

## Running Tests

```bash
# Run all E2E tests
npm run test:e2e

# Run with UI mode (interactive)
npm run test:e2e:ui

# Run in debug mode (step through)
npm run test:e2e:debug

# View test report
npm run test:e2e:report
```

## Prerequisites

1. **Backend running with DEBUG=true:**

    ```bash
    cd kitchen-agent
    DEBUG=true python -m uvicorn src.main:app --port 8000
    ```

2. **Frontend running:**
    ```bash
    cd kitchen-agent/frontend
    npm run dev
    ```

## Test Patterns

### Page Object Model

All page interactions are encapsulated in `ChatPage.ts`:

```typescript
const chatPage = new ChatPage(page);
await chatPage.goto();
await chatPage.loadSession('My Session');
await chatPage.deleteMessage(0);
await chatPage.expectMessageCount(3);
```

### Seed Fixtures

Test data is created via the `/api/_test/seed` endpoint:

```typescript
const session = await seedSession(page, { pairs: 3 });
// session.session_id, session.turn_ids available for assertions
```

### Cleanup

Sessions can be cleaned up after tests:

```typescript
test.afterAll(async ({ page }) => {
    await deleteSession(page, sessionId);
});
```

## Writing New Tests

1. **Use Page Object methods** instead of raw locators
2. **Seed test data** in `beforeEach` or at test start
3. **Wait for busy state** using `waitForBusyComplete()`
4. **Assert both UI and backend** state when relevant
5. **Test cancel flows** as well as success flows

## Debugging

- Use `--debug` flag to step through tests
- Use `--ui` flag for interactive mode
- Screenshots and videos are saved on failure in `e2e/test-results/`

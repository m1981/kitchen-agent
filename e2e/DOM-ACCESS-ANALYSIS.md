# DOM Access Issues Analysis

## Summary

Found **12 issues** across browser scripts and E2E tests that cause flaky behavior.

## Status

| Issue                               | Status     | Fix Applied                                                                 |
| ----------------------------------- | ---------- | --------------------------------------------------------------------------- |
| waitForTimeout anti-pattern         | ✅ Fixed   | Removed from ChatPage.ts, url-routing-title.spec.ts, message-delete.spec.ts |
| isVisible().catch() workaround      | ✅ Fixed   | Replaced with proper waitFor() in ChatPage.ts                               |
| page.evaluate() for DOM interaction | ✅ Fixed   | browser-seed.js now uses proper waiting                                     |
| textContent() without waiting       | ✅ Fixed   | Uses expect().toHaveText() or waitForFunction()                             |
| Complex locator chains              | ⚠️ Partial | Still used for token percentage                                             |
| Missing data-testid attributes      | ⚠️ Partial | Some elements still lack test IDs                                           |

---

## 🔴 Critical Issues (All Fixed)

### 1. `waitForTimeout` Anti-Pattern (8 occurrences)

**Files**: ChatPage.ts, message-delete.spec.ts, url-routing-title.spec.ts

```typescript
// ❌ BAD - Arbitrary delay, flaky on slow CI
await page.waitForTimeout(500);
await page.waitForTimeout(1000);
```

**Why it fails**:

- 500ms might be enough locally but not on CI
- Wastes time when 50ms would suffice
- Masks real timing issues

**Fix**: Use proper wait conditions:

```typescript
// ✅ GOOD - Wait for specific condition
await page.waitForFunction(() => /* condition */);
await expect(locator).toHaveText('expected');
await page.waitForLoadState('networkidle');
```

---

### 2. `isVisible().catch(() => false)` Workaround

**File**: ChatPage.ts:100

```typescript
// ❌ BAD - Catching errors hides real issues
const isVisible = await sessionButton.isVisible().catch(() => false);
if (!isVisible) {
    await this.page.reload();
    // ...
}
```

**Why it fails**:

- If element never appears, we reload and try again (infinite loop risk)
- Doesn't distinguish between "not loaded yet" vs "doesn't exist"
- Hides real bugs (wrong selector, missing element)

**Fix**: Use `waitForSelector` with proper timeout:

```typescript
// ✅ GOOD - Explicit wait with timeout
await sessionButton.waitFor({ state: 'visible', timeout: 10_000 });
```

---

### 3. `page.evaluate()` for DOM Interaction

**File**: browser-seed.js:108-130

```javascript
// ❌ BAD - Manual DOM queries in evaluate()
const clicked = await page.evaluate((title) => {
    const buttons = Array.from(document.querySelectorAll('aside button'));
    const btn = buttons.find((b) => b.textContent.trim().includes(title));
    if (btn) {
        btn.click();
        return true;
    }
    return false;
}, title);
```

**Why it fails**:

- No automatic waiting for elements
- No retry logic for stale elements
- Can't use Playwright's built-in auto-waiting

**Fix**: Use Playwright locators:

```javascript
// ✅ GOOD - Playwright auto-waits and retries
const sessionButton = page.locator(`aside button:has-text("${title}")`);
await sessionButton.waitFor({ state: 'visible', timeout: 10_000 });
await sessionButton.click();
```

---

## 🟡 Medium Issues

### 4. Fragile Text Content Reading

**File**: url-routing-title.spec.ts:147

```typescript
// ❌ BAD - Reads text before element is stable
const tokenText = await page.locator('text=/📊.*\\d/').textContent();
expect(tokenText).toBeTruthy();
```

**Why it fails**:

- `textContent()` can return partial content during render
- No wait for element to be fully rendered

**Fix**:

```typescript
// ✅ GOOD - Wait for specific content
await expect(page.locator('text=/📊.*\\d/')).toHaveText(/\d+/);
```

---

### 5. Complex Locator Chains

**File**: ChatPage.ts:209

```typescript
// ❌ BAD - Parent traversal is fragile
const text = await this.tokenProgressBar.locator('..').locator('..').textContent();
```

**Why it fails**:

- If DOM structure changes, breaks silently
- Multiple parent traversals are error-prone

**Fix**: Use `getByTestId` or semantic selectors:

```typescript
// ✅ GOOD - Stable test ID
const text = await this.page.getByTestId('token-percentage').textContent();
```

---

### 6. Missing `data-testid` Attributes

**Problem**: Many elements lack `data-testid`, forcing complex CSS selectors.

**Current state**:

- ✅ `chat-bubble`, `edit-btn`, `delete-btn`, `send-btn`
- ❌ Token percentage, session title, mode badge, context menu

**Fix**: Add `data-testid` to key elements in Svelte components.

---

## 🟢 Low Issues

### 7. Hardcoded Timeouts

**File**: ChatPage.ts:225

```typescript
// ⚠️ - Magic number timeout
await this.page.waitForTimeout(200);
```

**Fix**: Use named constants:

```typescript
const MENU_ANIMATION_MS = 200;
await this.page.waitForTimeout(MENU_ANIMATION_MS);
```

---

### 8. Missing Error Messages in Assertions

**File**: Various tests

```typescript
// ❌ BAD - No context on failure
await chatPage.expectMessageCount(4);
```

**Fix**:

```typescript
// ✅ GOOD - Descriptive error message
await chatPage.expectMessageCount(4, 'Session should have 4 messages after seed');
```

---

## Test Coverage Gaps

### Missing Tests for DOM Access Scenarios:

1. **Timing Tests**
    - Element appears after async operation
    - Element disappears after state change
    - Element updates content after API response

2. **Dynamic Content Tests**
    - List renders after `{#each}` completes
    - Conditional content appears after `{#if}` evaluates
    - Transitions complete before interaction

3. **Error State Tests**
    - Error toast appears and disappears
    - Loading spinner shows during async operations
    - Rollback restores previous DOM state

4. **Edge Cases**
    - Rapid clicks don't cause double-submit
    - Scroll position preserved after DOM update
    - Focus management after modal close

---

## Files to Fix

| File                        | Issues                                                | Priority |
| --------------------------- | ----------------------------------------------------- | -------- |
| `browser-seed.js`           | 3 (evaluate, timing, selectors)                       | High     |
| `ChatPage.ts`               | 4 (waitForTimeout, isVisible catch, complex locators) | High     |
| `url-routing-title.spec.ts` | 3 (waitForTimeout, textContent)                       | Medium   |
| `message-delete.spec.ts`    | 1 (waitForTimeout)                                    | Low      |

---

## Next Steps

1. Fix `browser-seed.js` to use Playwright locators
2. Update `ChatPage.ts` to remove `waitForTimeout` and `isVisible().catch()`
3. Add `data-testid` attributes to Svelte components
4. Create regression tests for timing scenarios
5. Run tests in loop to verify stability

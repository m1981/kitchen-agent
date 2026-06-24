# Visual E2E Tests Plan

**Status**: Draft
**Framework**: Playwright + TypeScript
**Base URL**: `http://localhost:5173`

---

## 1. Workflow — How We Work After Tests Are Active

### Daily Development Flow

```
1. Write feature code
2. Add/update visual tests for that feature
3. Run affected tests locally:  npx playwright test --grep "feature-name"
4. Run full suite before push:  npx playwright test
5. CI runs on every PR → merge gate
```

### Test-First for Visual Changes

When modifying any UI component:

1. **Before change** — run existing tests, capture baseline screenshot
2. **Make the change** — implement the feature/fix
3. **Update tests** — adjust selectors, add new test cases
4. **Verify** — run tests, review screenshot diffs
5. **Commit** — tests must pass before commit

### When to Run What

| Scenario                     | Command                                          | Time   |
| ---------------------------- | ------------------------------------------------ | ------ |
| Quick check (single feature) | `npx playwright test --grep "sidebar"`           | ~15s   |
| Full regression              | `npx playwright test`                            | ~2min  |
| Visual diff review           | `npx playwright test --update-snapshots`         | ~2min  |
| Debug flaky test             | `npx playwright test --debug --grep "test name"` | manual |
| CI/CD                        | `npx playwright test` (all tags)                 | ~2min  |

### Branch Protection Rules

- All `@smoke` tests must pass to merge
- Visual snapshot diffs require manual review
- New features require corresponding test additions
- Breaking changes require test updates in same PR

---

## 2. Test Structure — File Organization

```
e2e/
├── fixtures/
│   ├── base.ts                 # Custom test fixture with ChatPage
│   └── seed.ts                 # API-based test data setup
├── page-objects/
│   ├── ChatPage.ts             # Main chat page (existing, extend)
│   ├── SidebarPage.ts          # Left sidebar interactions
│   ├── ComposerPage.ts         # Composer area interactions
│   └── ContextSidebarPage.ts   # Right sidebar interactions
├── visual/                     # Visual regression tests
│   ├── layouts/
│   │   ├── desktop.spec.ts     # Desktop 3-panel layout
│   │   ├── mobile.spec.ts      # Mobile overlay layout
│   │   └── responsive.spec.ts  # Breakpoint transitions
│   ├── components/
│   │   ├── system-prompt.spec.ts
│   │   ├── composer.spec.ts
│   │   ├── token-strip.spec.ts
│   │   └── sidebar-toggle.spec.ts
│   └── states/
│       ├── empty-session.spec.ts
│       ├── streaming.spec.ts
│       └── error-states.spec.ts
├── features/                   # Behavioral E2E tests
│   ├── chat/
│   │   ├── messaging.spec.ts
│   │   ├── streaming.spec.ts
│   │   ├── editing.spec.ts
│   │   └── deletion.spec.ts
│   ├── sessions/
│   │   ├── routing.spec.ts
│   │   ├── folders.spec.ts
│   │   ├── archive.spec.ts
│   │   └── drag-drop.spec.ts
│   ├── composer/
│   │   ├── model-selector.spec.ts
│   │   ├── tools-toggle.spec.ts
│   │   └── image-paste.spec.ts
│   └── sidebar/
│       ├── resize.spec.ts
│       ├── notes.spec.ts
│       └── context-files.spec.ts
├── playwright.config.ts
└── tests/                      # Existing tests (migrate over time)
```

### Naming Conventions

| Pattern     | Example           | Purpose              |
| ----------- | ----------------- | -------------------- |
| `*.spec.ts` | `desktop.spec.ts` | Playwright test file |
| `*Page.ts`  | `ChatPage.ts`     | Page object class    |
| `seed.ts`   | `seed.ts`         | Test data fixtures   |

### Tag Strategy

| Tag           | Meaning                 | When to Run            |
| ------------- | ----------------------- | ---------------------- |
| `@smoke`      | Critical path, <5s each | Every deploy, every PR |
| `@visual`     | Screenshot comparison   | PR review, nightly     |
| `@regression` | Full coverage           | PR, nightly            |
| `@mobile`     | Mobile-specific tests   | When layout changes    |
| `@desktop`    | Desktop-specific tests  | When layout changes    |
| `@slow`       | Long-running (>10s)     | Nightly only           |

---

## 3. Test Plan — By Feature Area

### 3.1 Layout & Navigation

#### Desktop Layout (`@smoke @desktop`)

| #   | Test Case                            | Validates                             |
| --- | ------------------------------------ | ------------------------------------- |
| 1   | Three-panel layout renders correctly | Sidebar, chat, context panels visible |
| 2   | Sidebar toggle hides left panel      | Sidebar disappears, chat expands      |
| 3   | Sidebar toggle shows left panel      | Sidebar reappears, chat shrinks       |
| 4   | Context panel toggle works           | Right panel shows/hides               |
| 5   | Sidebar resize via drag              | Width changes, content reflows        |
| 6   | Sidebar width persists after reload  | localStorage persistence              |

#### Mobile Layout (`@smoke @mobile`)

| #   | Test Case                               | Validates                       |
| --- | --------------------------------------- | ------------------------------- | ----------------- |
| 1   | Sidebar hidden by default               | No sidebar on mobile            |
| 2   | Toggle button visible                   | `                               | □` icon in header |
| 3   | Sidebar opens as overlay                | Drawer with backdrop            |
| 4   | Backdrop tap closes sidebar             | Click backdrop → sidebar closes |
| 5   | Toggle button closes sidebar            | Click toggle → sidebar closes   |
| 6   | Chat fills viewport when sidebar closed | No horizontal scroll            |

#### Responsive Breakpoints (`@visual @regression`)

| #   | Test Case                        | Viewports                    |
| --- | -------------------------------- | ---------------------------- |
| 1   | Layout at 320px (small phone)    | iPhone SE                    |
| 2   | Layout at 390px (iPhone 13)      | iPhone 13                    |
| 3   | Layout at 768px (tablet)         | iPad                         |
| 4   | Layout at 1024px (small desktop) | Desktop                      |
| 5   | Layout at 1440px (wide desktop)  | Desktop                      |
| 6   | Breakpoint transitions           | Resize from mobile → desktop |

---

### 3.2 Chat & Messaging

#### Empty State (`@smoke`)

| #   | Test Case                          | Validates                             |
| --- | ---------------------------------- | ------------------------------------- |
| 1   | New session shows empty chat       | No messages, system prompt visible    |
| 2   | System prompt collapsed by default | Single-line header, chevron visible   |
| 3   | System prompt expands on click     | Full prompt text visible              |
| 4   | Composer ready for input           | Textarea focused, send button enabled |

#### Message Display (`@regression`)

| #   | Test Case                       | Validates                    |
| --- | ------------------------------- | ---------------------------- |
| 1   | User messages right-aligned     | Blue bubble, right side      |
| 2   | Assistant messages left-aligned | White bubble, left side      |
| 3   | Markdown renders correctly      | Bold, lists, code blocks     |
| 4   | Tool logs expandable            | Click "View" → details shown |
| 5   | Token count shown per message   | Badge visible on messages    |
| 6   | Model badge shown on assistant  | Model name visible           |

#### Streaming (`@regression`)

| #   | Test Case                            | Validates               |
| --- | ------------------------------------ | ----------------------- |
| 1   | Pulsing indicator during streaming   | Animated dot visible    |
| 2   | Stop button appears during streaming | Red circle button       |
| 3   | Navigation blocked during streaming  | `beforeNavigate` cancel |
| 4   | Message appears after streaming      | Full response visible   |

#### Message Editing (`@regression`)

| #   | Test Case                    | Validates                      |
| --- | ---------------------------- | ------------------------------ |
| 1   | Edit button appears on hover | Button visible on user message |
| 2   | Click edit opens textarea    | Inline editor appears          |
| 3   | Save edit updates message    | Content changes                |
| 4   | Cancel edit reverts          | Original content restored      |
| 5   | Edit truncates history       | Messages after edit removed    |

#### Message Deletion (`@regression`)

| #   | Test Case                          | Validates                           |
| --- | ---------------------------------- | ----------------------------------- |
| 1   | Delete button appears on hover     | Button visible                      |
| 2   | Click delete shows confirm dialog  | Dialog appears                      |
| 3   | Confirm deletes message            | Message removed from list           |
| 4   | Cancel keeps message               | Dialog closes, message stays        |
| 5   | User message auto-promotes to pair | Delete user → deletes assistant too |

---

### 3.3 Session Management

#### URL Routing (`@smoke`)

| #   | Test Case                       | Validates             |
| --- | ------------------------------- | --------------------- |
| 1   | `/` redirects to `/chat/{uuid}` | URL updates           |
| 2   | Direct URL loads session        | `/chat/{id}` works    |
| 3   | Refresh preserves session       | F5 keeps same session |
| 4   | Back button navigates           | Browser history works |
| 5   | New session gets new URL        | `goto()` updates URL  |

#### Session Title (`@regression`)

| #   | Test Case              | Validates               |
| --- | ---------------------- | ----------------------- |
| 1   | Title shown in header  | Text visible            |
| 2   | Click title to edit    | Input appears           |
| 3   | Enter saves title      | Title updates           |
| 4   | Escape cancels edit    | Original title restored |
| 5   | Title shown in sidebar | Text visible in list    |

#### Session Folders (`@regression`)

| #   | Test Case                            | Validates        |
| --- | ------------------------------------ | ---------------- |
| 1   | Folder tree renders                  | Folders visible  |
| 2   | Expand folder shows sessions         | Sessions listed  |
| 3   | Create folder dialog                 | Input appears    |
| 4   | Drag session to folder               | Session moves    |
| 5   | Foldered session hidden from History | Not in main list |

#### Session Archive (`@regression`)

| #   | Test Case                        | Validates       |
| --- | -------------------------------- | --------------- |
| 1   | Archive section collapsed        | Arrow visible   |
| 2   | Expand shows archived sessions   | Sessions listed |
| 3   | Archive session moves to Archive | Session moves   |
| 4   | Unarchive restores to History    | Session returns |

---

### 3.4 Composer

#### Composer Layout (`@smoke`)

| #   | Test Case                       | Validates               |
| --- | ------------------------------- | ----------------------- |
| 1   | Composer visible at bottom      | Footer present          |
| 2   | Textarea auto-resizes           | Height grows with input |
| 3   | Send button circular blue       | Icon-only button        |
| 4   | Send button disabled when empty | Grayed out              |

#### Tools Toggle (`@regression`)

| #   | Test Case                   | Validates     |
| --- | --------------------------- | ------------- |
| 1   | Tools ON by default         | Blue border   |
| 2   | Click toggles state         | Color changes |
| 3   | State persists after reload | localStorage  |

#### Model Selector (`@regression`)

| #   | Test Case                   | Validates       |
| --- | --------------------------- | --------------- |
| 1   | Dropdown shows models       | Options visible |
| 2   | Select changes model        | Value updates   |
| 3   | Model persists after reload | localStorage    |

#### Token Strip (`@visual`)

| #   | Test Case               | Validates          |
| --- | ----------------------- | ------------------ |
| 1   | Hidden when <10%        | No bar visible     |
| 2   | Yellow at 10-20%        | Yellow bar         |
| 3   | Orange at 20-30%        | Orange bar         |
| 4   | Red at >30%             | Red bar            |
| 5   | Full-width progress bar | Bar spans composer |

---

### 3.5 Context Sidebar

#### Context Files (`@regression`)

| #   | Test Case                       | Validates          |
| --- | ------------------------------- | ------------------ |
| 1   | Files listed with checkboxes    | List visible       |
| 2   | Check file adds to context      | Checkbox checked   |
| 3   | Uncheck removes from context    | Checkbox unchecked |
| 4   | Context files shown in composer | Strip visible      |
| 5   | Remove from composer strip      | File removed       |

#### Notes (`@regression`)

| #   | Test Case                 | Validates                        |
| --- | ------------------------- | -------------------------------- |
| 1   | Notes tab visible         | Tab clickable                    |
| 2   | Create note               | Note appears                     |
| 3   | Edit note                 | Content updates                  |
| 4   | Delete note               | Note removed                     |
| 5   | Notes persist per session | Switch sessions, notes preserved |

#### Text Selection → Note (`@regression`)

| #   | Test Case                  | Validates         |
| --- | -------------------------- | ----------------- |
| 1   | Select text shows popup    | NotePopup appears |
| 2   | Click popup creates note   | Note saved        |
| 3   | Click away dismisses popup | Popup disappears  |

---

### 3.6 System Prompt

#### System Prompt Bubble (`@smoke`)

| #   | Test Case                  | Validates               |
| --- | -------------------------- | ----------------------- |
| 1   | Collapsed by default       | Single line visible     |
| 2   | Shows mode badge           | "General" badge visible |
| 3   | Shows "Not set" when empty | Text visible            |
| 4   | Expand shows full text     | Full prompt visible     |
| 5   | Collapse hides text        | Back to single line     |

#### System Prompt Editing (`@regression`)

| #   | Test Case                     | Validates         |
| --- | ----------------------------- | ----------------- |
| 1   | Click edit icon opens editor  | Textarea appears  |
| 2   | Type new prompt               | Text updates      |
| 3   | Save with ⌘↵                  | Prompt saved      |
| 4   | Cancel with Esc               | Original restored |
| 5   | Override badge shows "custom" | Badge visible     |

---

## 4. Page Objects — Required Additions

### Extend Existing `ChatPage.ts`

Add locators for new components:

```typescript
// Add to ChatPage.ts constructor

// Sidebar toggle
this.sidebarToggle = page.locator('header button[aria-label*="sidebar"]');
this.leftSidebar = page.locator('aside').first();
this.mobileBackdrop = page.locator('[aria-label="Close sidebar"]');

// System prompt
this.systemPromptBubble = page.locator('[aria-label="System prompt"]');
this.systemPromptToggle = page.locator('[aria-label="System prompt"] button');
this.systemPromptExpand = page.locator('[aria-label="System prompt"] button[aria-expanded]');

// Composer (updated)
this.sendButtonCircle = page.getByTestId('send-btn');
this.toolsToggle = page.locator('.tools-btn');

// Token strip
this.tokenStrip = page.locator('[role="progressbar"]');
```

### New `SidebarPage.ts`

```typescript
export class SidebarPage {
    constructor(private page: Page) {}

    async toggle() { ... }
    async isVisible(): Promise<boolean> { ... }
    async getSessionCount(): Promise<number> { ... }
    async searchSession(query: string) { ... }
    async dragSessionToFolder(session: string, folder: string) { ... }
}
```

### New `ComposerPage.ts`

```typescript
export class ComposerPage {
    constructor(private page: Page) {}

    async typeMessage(text: string) { ... }
    async send() { ... }
    async toggleTools() { ... }
    async selectModel(model: string) { ... }
    async getPastedImageCount(): Promise<number> { ... }
}
```

---

## 5. Selectors Strategy

### Priority Order (follow existing patterns)

| Priority | Strategy          | Example                                             |
| -------- | ----------------- | --------------------------------------------------- |
| 1        | `data-testid`     | `page.getByTestId('chat-bubble')`                   |
| 2        | `aria-label`      | `page.locator('button[aria-label="Hide sidebar"]')` |
| 3        | Role + name       | `page.getByRole('button', { name: /send/i })`       |
| 4        | CSS (last resort) | `page.locator('.composer-box')`                     |

### Existing Test IDs (maintain these)

| Component         | Test ID             | Element      |
| ----------------- | ------------------- | ------------ |
| Chat bubbles      | `chat-bubble`       | `<article>`  |
| Chat input        | `chat-input`        | `<textarea>` |
| Send button       | `send-btn`          | `<button>`   |
| Stop button       | `stop-btn`          | `<button>`   |
| Loading indicator | `loading-indicator` | `<article>`  |
| Confirm dialog    | `confirm-dialog`    | `<div>`      |
| App busy          | `app-busy`          | `<div>`      |

### New Test IDs to Add

| Component            | Test ID          | Element     |
| -------------------- | ---------------- | ----------- |
| Sidebar toggle       | `sidebar-toggle` | `<button>`  |
| System prompt bubble | `system-prompt`  | `<article>` |
| Token strip          | `token-strip`    | `<div>`     |
| Tools toggle         | `tools-toggle`   | `<button>`  |
| Model selector       | `model-selector` | `<select>`  |

---

## 6. Visual Snapshot Strategy

### When to Take Snapshots

| Scenario         | Snapshot          | Compare          |
| ---------------- | ----------------- | ---------------- |
| New layout       | Full page         | Baseline         |
| Component change | Component only    | Previous version |
| Responsive test  | Viewport-specific | Other viewports  |
| State change     | Same viewport     | Before/after     |

### Snapshot Naming Convention

```
tests/visual/__screenshots__/
├── desktop/
│   ├── empty-session.png
│   ├── with-messages.png
│   └── sidebar-collapsed.png
├── mobile/
│   ├── empty-session.png
│   ├── sidebar-open.png
│   └── sidebar-closed.png
└── components/
    ├── system-prompt-collapsed.png
    ├── system-prompt-expanded.png
    └── token-strip-states.png
```

### Snapshot Rules

1. **Never commit flaky snapshots** — deterministic data only
2. **Seed data for snapshots** — consistent API responses
3. **Mask dynamic content** — timestamps, IDs, counts
4. **Review diffs manually** — never auto-approve
5. **Update snapshots intentionally** — `--update-snapshots` flag

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1)

- [ ] Extend `ChatPage.ts` with new locators
- [ ] Create `SidebarPage.ts` page object
- [ ] Create `ComposerPage.ts` page object
- [ ] Add missing `data-testid` attributes to components
- [ ] Set up visual snapshot infrastructure

### Phase 2: Critical Path (`@smoke`) (Week 2)

- [ ] Desktop layout tests
- [ ] Mobile layout tests
- [ ] Empty session state
- [ ] URL routing tests
- [ ] Composer readiness

### Phase 3: Core Features (`@regression`) (Week 3)

- [ ] Chat messaging (display, streaming)
- [ ] Message editing/deletion
- [ ] Session title management
- [ ] Tools toggle
- [ ] Model selector

### Phase 4: Advanced Features (`@regression`) (Week 4)

- [ ] Session folders
- [ ] Session archive
- [ ] Context files
- [ ] Notes
- [ ] Text selection → note

### Phase 5: Visual Polish (`@visual`) (Week 5)

- [ ] System prompt states
- [ ] Token strip colors
- [ ] Responsive breakpoints
- [ ] Error states
- [ ] Loading states

---

## 8. Metrics & Monitoring

### Test Health Metrics

| Metric                    | Target | Alert  |
| ------------------------- | ------ | ------ |
| Test pass rate            | >98%   | <95%   |
| Flaky test rate           | <2%    | >5%    |
| Average test time         | <3s    | >10s   |
| Snapshot diff review time | <5min  | >15min |

### Review Process

1. **PR opens** → CI runs all `@smoke` + `@regression` tests
2. **Snapshot diffs** → automatically posted as PR comment
3. **Manual review** → approve or request changes
4. **Merge** → only if all tests pass
5. **Nightly** → full suite including `@slow`

---

## Appendix A: Existing Test Files to Migrate

| Current Location                          | Target Location                                | Notes |
| ----------------------------------------- | ---------------------------------------------- | ----- |
| `e2e/tests/truncate.spec.ts`              | `e2e/features/chat/messaging.spec.ts`          |       |
| `e2e/tests/url-routing-title.spec.ts`     | `e2e/features/sessions/routing.spec.ts`        |       |
| `e2e/tests/message-delete.spec.ts`        | `e2e/features/chat/deletion.spec.ts`           |       |
| `e2e/tests/inbox-model.spec.ts`           | `e2e/features/composer/model-selector.spec.ts` |       |
| `e2e/tests/regenerate.spec.ts`            | `e2e/features/chat/messaging.spec.ts`          |       |
| `e2e/tests/dom-access-regression.spec.ts` | `e2e/visual/states/error-states.spec.ts`       |       |

---

## Appendix B: Commands Quick Reference

```bash
# Run all tests
npx playwright test

# Run smoke tests only
npx playwright test --grep "@smoke"

# Run visual tests only
npx playwright test --grep "@visual"

# Run mobile tests only
npx playwright test --grep "@mobile"

# Run single test file
npx playwright test e2e/visual/layouts/desktop.spec.ts

# Debug mode
npx playwright test --debug --grep "sidebar toggle"

# Update snapshots
npx playwright test --update-snapshots

# Generate HTML report
npx playwright show-report e2e/test-results/html

# Run with UI mode
npx playwright test --ui
```

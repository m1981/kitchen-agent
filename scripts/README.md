# Project Scripts

Browser automation scripts specific to Kitchen Agent.

These scripts depend on Kitchen Agent's API endpoints (`/api/_test/seed`, `X-Test-Delay-Ms` header) and should NOT be moved to global skills.

## Scripts

### `browser-seed.js`

Create a test session with N turn-pairs and navigate to it.

```bash
scripts/browser-seed.js --pairs 3 --title "My Test"
```

Requires: `DEBUG=true` on backend.

### `browser-intercept.js`

Intercept and control API responses for testing.

```bash
# Slow down responses to test loading states
scripts/browser-intercept.js --path '/api/sessions/*/messages/*' --delay 2000

# Simulate server error
scripts/browser-intercept.js --path '/api/chat' --status 500 --error "Server error"

# Clear all intercepts
scripts/browser-intercept.js --clear
```

## Generic Browser Tools

For generic browser automation (navigation, screenshots, DOM queries), use the tools in `~/.pi/agent/skills/pi-skills/browser-tools/`:

- `browser-test.js` — click, query, assert, confirm
- `browser-wait.js` — wait for DOM conditions
- `browser-eval.js` — evaluate JavaScript
- `browser-nav.js` — navigate to URLs
- `browser-screenshot.js` — capture screenshots

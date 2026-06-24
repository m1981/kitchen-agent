# Feature Catalog

Single source of truth for every user-facing feature. Documents design
decisions, scope, and persistence. For implementation details, see linked
specs and source files.

> **How to maintain**: Add a section when you add a feature. Update the
> "Design decision" field when you change behavior. Keep it short — link
> to specs for depth.

---

## Table of Contents

- [Chat & Messaging](#chat--messaging)
    - [Message Streaming](#message-streaming)
    - [Message Editing](#message-editing)
    - [Message Deletion](#message-deletion)
    - [Session Fork](#session-fork)
    - [Image Paste](#image-paste)
    - [Context Files](#context-files)
    - [System Prompt Override](#system-prompt-override)
- [Model & Provider](#model--provider)
    - [Model Selector](#model-selector)
    - [Tools Toggle](#tools-toggle)
    - [Prompt Modes](#prompt-modes)
- [Session Management](#session-management)
    - [URL-Based Routing](#url-based-routing)
    - [Session Title](#session-title)
    - [Session Folders](#session-folders)
    - [Session Archive](#session-archive)
    - [Session Import/Export](#session-importexport)
    - [Drag & Drop](#drag--drop)
- [Sidebar & Layout](#sidebar--layout)
    - [Sidebar Toggle](#sidebar-toggle)
    - [Sidebar Resize](#sidebar-resize)
    - [Notes](#notes)
    - [Text Selection → Note](#text-selection--note)
    - [Token Indicator](#token-indicator)

---

## Chat & Messaging

### Message Streaming

**What**: Assistant responses stream in real-time via SSE. Tool calls and
results are displayed inline as they happen.

**Scope**: Per-session (state lives in `chatStore.messages[]`)

**Persisted**: Backend — `sessions.ui_history_json`

**Design decision**: Streaming uses a single SSE connection per message.
The UI shows a pulsing indicator while `isStreaming === true`. Navigation
is blocked during streaming (`beforeNavigate → cancel()`).

**Spec**: [frontend-diagrams.md §4](specs/frontend-diagrams.md)

---

### Message Editing

**What**: User can edit any of their past messages. The edit saves a new
version; the original is preserved in the API history.

**Scope**: Per-session

**Persisted**: Backend — `sessions.api_history_json`

**Design decision**: Editing a user message triggers a backend truncation —
all messages after the edit point are removed from the API history. The UI
history is updated in place. No re-generation happens automatically.

**Spec**: [editor.svelte.ts](../frontend/src/lib/stores/editor.svelte.ts)

---

### Message Deletion

**What**: User can delete a single message or a user+assistant pair.

**Scope**: Per-session

**Persisted**: Backend — removes from `sessions.api_history_json`

**Design decision**: If the selected message is a user message and the user
chooses "delete single", the system auto-promotes to pair-delete (removes
the user message and its assistant response). This prevents orphaned user
messages without answers.

**Spec**: [editor.svelte.ts](../frontend/src/lib/stores/editor.svelte.ts)

---

### Session Fork

**What**: User can fork a session at any turn — creates a new session that
copies all messages up to that point.

**Scope**: Creates a new session (parent → child relationship)

**Persisted**: Backend — `sessions.parent_id`, `sessions.fork_turn_index`

**Design decision**: Forked sessions appear in History. The parent cannot
be deleted while it has children. Fork children can be independently
archived, foldered, or deleted (if they have no children of their own).

**Spec**: [session-state-machine.md](specs/session-state-machine.md)

---

### Image Paste

**What**: User can paste images from clipboard (Ctrl+V) into the chat
composer. Images are sent as base64 with the next message.

**Scope**: Per-message (queued in `chatStore.pastedImages[]`, cleared after send)

**Persisted**: No — images are not stored, only sent with the message

**Design decision**: Images are extracted from the clipboard's first
`image/png` entry. Multiple pastes queue up. The preview strip shows
thumbnails. Only supported for providers that accept images (Gemini).

**Spec**: [pasteImage.ts](../frontend/src/lib/actions/pasteImage.ts)

---

### Context Files

**What**: User can attach knowledge-base files to a conversation. The
selected files are sent with every message as additional context.

**Scope**: Per-session (stored in `chatStore.contextFiles[]`)

**Persisted**: No — cleared on session switch, re-selected manually

**Design decision**: Context files are file paths from the knowledge base,
not uploaded files. The backend reads them and includes their content in the
LLM context. Token estimates for context files are refreshed on change.

**Spec**: [ContextSidebar.svelte](../frontend/src/lib/components/ContextSidebar.svelte)

---

### System Prompt Override

**What**: User can view and edit the system prompt for the current session.
The prompt bubble is collapsed by default — a single-line header with a
chevron. Click to expand and inspect or edit.

**Scope**: Per-session

**Persisted**: Backend — `sessions.system_prompt`

**Design decision**: Each session stores its own system prompt override.
When loading a session, the override is fetched. If empty, the mode's
default prompt is used. The bubble starts collapsed to reduce visual noise;
only the header line (mode label + chevron) is visible by default.

**Spec**: [editor.svelte.ts](../frontend/src/lib/stores/editor.svelte.ts)

---

## Model & Provider

### Model Selector

**What**: Dropdown to select LLM provider and model. Two-level: provider
first, then model within that provider.

**Scope**: Per-session (synced from last assistant message on session load)

**Persisted**: Yes — localStorage `ka:provider`, `ka:model`

**Design decision**: Model choice follows the conversation. When you load
a session that used Gemini, the picker restores Gemini. New chats keep
the user's last manual choice. Provider/model is NOT stored per-session
in the backend — it's inferred from the message history.

**Spec**: [provider.svelte.ts](../frontend/src/lib/stores/provider.svelte.ts)

---

### Tools Toggle

**What**: Button to enable/disable the agentic tool loop. When OFF, the
LLM responds directly without accessing the knowledge base.

**Scope**: Global (same state across all sessions)

**Persisted**: Yes — localStorage `ka:tools` (default: `true`)

**Design decision**: Tools is a user preference, not a per-session setting.
The LLM either has access to the knowledge base or it doesn't — this
doesn't change between conversations. The toggle syncs to the prompt
mode's `tools_enabled_default` when the mode changes, but the user can
override it.

**Known limitation**: Button text says "Tools" in both states — visual
feedback is color-only (blue when ON, white when OFF).

**Spec**: [prompt.svelte.ts](../frontend/src/lib/stores/prompt.svelte.ts)

---

### Prompt Modes

**What**: Dropdown to select the LLM's persona/role. Each mode has a
different system prompt and optional tool configuration.

**Scope**: Global (persists across sessions)

**Persisted**: Yes — localStorage `ka:mode` (default: `'general'`)

**Design decision**: Three modes: General (workspace help), Design
(ergonomics and layout), Assembly (build and fitting). Each mode maps to
a markdown file in `prompts/`. The mode's `tools_enabled_default` syncs
to the tools toggle when the mode changes.

**Spec**: [modes.json](../prompts/modes.json), [prompt.svelte.ts](../frontend/src/lib/stores/prompt.svelte.ts)

---

## Session Management

### URL-Based Routing

**What**: Each session has a unique URL (`/chat/{uuid}`). The URL is the
source of truth for the active session.

**Scope**: Per-session

**Persisted**: URL (browser history)

**Design decision**: Opening `/` redirects to `/chat/{new-uuid}`. Refreshing
the page restores the session from the backend. Navigating to a new session
updates the URL via `goto()`. Streaming blocks navigation (`beforeNavigate →
cancel()`).

**Spec**: [url-routing-implementation.md](url-routing-implementation.md)

---

### Session Title

**What**: Sessions display a title in the sidebar. Titles are auto-generated
after the first message, manually editable, and regeneratable.

**Scope**: Per-session

**Persisted**: Backend — `sessions.title`

**Design decision**: On first message, the first 30 characters of the user
message are used as a temporary title. A background request to
`POST /api/sessions/{id}/title/generate` uses claude-haiku to generate a
concise title (max 50 chars). The title is editable inline in the header.
Context menu offers "✨ Regenerate Title".

**Spec**: [title-feature-edge-cases.md](title-feature-edge-cases.md)

---

### Session Folders

**What**: Sessions can be organized into colored folders. A session can
belong to multiple folders (many-to-many). Sessions in folders are hidden
from History.

**Scope**: Per-session (many-to-many relationship)

**Persisted**: Backend — `session_folders` table

**Design decision**: Foldered sessions disappear from History to avoid
duplication. The folder tree supports expand/collapse with per-folder
session lists. Folder operations are optimistic with rollback on error.
`folderedSessionIds` (SvelteSet) tracks which sessions are in any folder
for O(1) visibility checks.

**Spec**: [f003-folder-organization.md](specs/f003-folder-organization.md)

---

### Session Archive

**What**: Sessions can be archived to hide them without deletion. Archived
sessions appear in a collapsible Archive section.

**Scope**: Per-session

**Persisted**: Backend — `sessions.archived_at`

**Design decision**: Archiving a session that is in a folder asks the user
to remove it from the folder first. Archiving a fork parent asks whether
to include children. Archived sessions cannot be messaged, forked, or
moved to folders. Unarchive restores to History (or folder if still
assigned).

**Spec**: [session-state-machine.md](specs/session-state-machine.md)

---

### Session Import/Export

**What**: Sessions can be exported as Markdown (human-readable) or LLM JSON
(machine-readable). External JSON files can be imported.

**Scope**: Per-session

**Persisted**: Backend — creates new session on import

**Design decision**: Export formats: (1) Markdown — renders the conversation
as formatted text, (2) LLM JSON — includes `api_history` for replay.
Import accepts a JSON array of messages with role/content. Imported
sessions get a derived title from the first user message.

**Spec**: [f002-import-export.md](specs/f002-import-export.md)

---

### Drag & Drop

**What**: Sessions can be dragged from the session list into folders.

**Scope**: Per-session

**Persisted**: Backend — `session_folders` table

**Design decision**: Uses native HTML5 drag events via Svelte actions
(`use:draggable`, `use:droppable`). Each folder acts as a drop zone.
`folderStore.pendingOps` (SvelteMap) tracks in-flight operations for
UX feedback. Drag is disabled during streaming.

**Spec**: [drag-drop-analysis.md](specs/drag-drop-analysis.md)

---

## Sidebar & Layout

### Sidebar Toggle

**What**: Header buttons to toggle left (session) and right (context) sidebars.
On mobile, the left sidebar opens as an overlay drawer with a backdrop.

**Scope**: Global (persists across sessions)

**Persisted**: Yes — localStorage `kitchen-agent:layout:left-sidebar-visible`,
`kitchen-agent:layout:right-sidebar-visible`

**Design decision**: Both sidebars start visible. Toggling persists the
state so the layout survives refresh. On mobile (<lg breakpoint), the
left sidebar becomes a full-height overlay with a semi-transparent backdrop
tap-to-close. Header z-index is above the sidebar for toggle accessibility.

**Spec**: [sidebar-resize.svelte.ts](../frontend/src/lib/sidebar-resize.svelte.ts)

---

### Sidebar Resize

**What**: The sidebar width is adjustable by dragging or keyboard shortcuts.
The composer height is also adjustable.

**Scope**: Global (persists across sessions)

**Persisted**: Yes — localStorage `kitchen-agent:layout:left-sidebar-width`,
`kitchen-agent:layout:right-sidebar-width`,
`kitchen-agent:layout:prompt-height`

**Design decision**: Sizes persist so the user's layout preference survives
page refreshes. Keyboard shortcuts (arrow keys when focused) provide
accessible resizing. Minimum/maximum widths are enforced. Double-click
resets to default.

**Spec**: [sidebar-resize.svelte.ts](../frontend/src/lib/sidebar-resize.svelte.ts)

---

### Notes

**What**: Users can create short notes attached to a session. Notes are
keyed by session ID.

**Scope**: Per-session

**Persisted**: Backend — `notes` table

**Design decision**: Notes are loaded on-demand per session. The store
caches them in `bySession` (Record<string, Note[]>) so switching back to
a session doesn't re-fetch. Notes are created via the NotePopup (from
text selection) or the NotesPanel.

**Spec**: [notes.svelte.ts](../frontend/src/lib/stores/notes.svelte.ts)

---

### Text Selection → Note

**What**: Selecting text in a chat message shows a popup to create a note
from the selection.

**Scope**: Per-session

**Persisted**: Backend — `notes` table

**Design decision**: The `use:textSelection` action listens for mouseup
events and checks if the selection is within a message bubble. If so, it
fires a callback with the selected text and position. The NotePopup
renders at page level (portal pattern) near the selection.

**Spec**: [textSelection.ts](../frontend/src/lib/actions/textSelection.ts)

---

### Token Indicator

**What**: Colored strip bar showing context window usage. Hidden when usage
is low, then transitions yellow → orange → red as usage grows.

**Scope**: Per-session (reads from `tokenStore`)

**Persisted**: No — computed on the fly from API response

**Design decision**: The strip replaces the previous text-based indicator
(bars, session count, input count, percentage). Color thresholds: hidden
(<10%), yellow (10-20%), orange (20-30%), red (>30%). Input tokens are
estimated locally before sending. Context window size comes from the
selected model's `context_k` field.

**Spec**: [TokenIndicator.svelte](../frontend/src/lib/components/TokenIndicator.svelte)

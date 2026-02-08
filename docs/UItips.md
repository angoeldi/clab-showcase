# Modern chat UI/UX principles (frontend dev)

A good chat UI is a *log* (reliable, readable, navigable) plus a *composer* (fast, forgiving, expressive). Everything else serves those two.

## 1) Information architecture

### Conversation list
- **Stable identity:** distinct title, avatar, last message preview, timestamp, unread badge.
- **Predictable ordering:** sort by most recent activity; avoid silent reorders while the user is scanning.
- **Search-first:** global search across conversations and messages; show highlighted matches and jump targets.
- **Draft persistence:** show “Draft” state per thread; never lose composer text on navigation.

### In-conversation structure
- Treat the transcript as an append-only timeline with *local edits* (edit, delete, react) rather than reflowing history.
- If you support threads, keep the main timeline readable:
  - Inline “n replies” affordance.
  - Side panel or focused view that keeps context visible (quoted parent + thread).

## 2) Layout and reading ergonomics

### Bubble design
- **Left/right alignment:** consistent mapping (self vs others). For assistant tools, consider a third style (system/tool) that is visually distinct but not loud.
- **Line length:** cap bubble width (roughly 60–75 chars per line equivalent) for readability on desktop; allow wider on mobile.
- **Whitespace is UX:** message density should be adjustable via compact/comfortable modes.

### Timestamps and grouping
- **Group consecutive messages** from the same sender if within a short interval; reduce repeated avatars/names.
- **Progressive disclosure for time:** subtle per-bubble time on hover/focus; stronger separators (“Today”, “Yesterday”) when date changes.
- **Edits:** mark edited messages with a small “edited” indicator; provide edit history only if necessary.

### Scroll behavior (the hardest part)
- **Auto-scroll only when the user is at the bottom** (or “near bottom” threshold). If the user scrolls up, stop auto-scrolling.
- When new messages arrive while scrolled up:
  - show a **“New messages”** chip/button that jumps down
  - preserve reading position precisely (scroll anchoring)
- **Maintain input visibility** on mobile when the keyboard opens (use safe-area insets; avoid layout jumps).

Implementation note: prefer an explicit “stick to bottom” state rather than guessing every render.

## 3) The composer: speed, forgiveness, expressiveness

### Input field
- **Auto-resize textarea** up to a sensible max height; then internal scroll.
- Support **multiline with Shift+Enter**, send with Enter (configurable).
- Keep **Send** enabled state predictable (trim whitespace; show disabled reason only when needed).

### Attachments and rich input
- Drag/drop, paste image, file picker.
- Upload UX:
  - thumbnail previews
  - per-file progress
  - cancel/retry
  - clear error copy (“Upload failed. Retry.”)
- Link preview should be *non-blocking*: render message immediately; attach preview when ready.

### Drafts and recovery
- Persist drafts per conversation (local storage or IndexedDB).
- If the page reloads mid-message, recover draft and attachments (when feasible).

## 4) Message-level interaction patterns

### Primary actions (keep minimal)
- Hover/tap menu: reply, react, copy, edit (self), delete (self), report (others).
- Long-press on mobile mirrors hover menu on desktop.
- “Copy” should copy *clean text* by default; offer “Copy as Markdown” or “Copy link” when relevant.

### Reply/quote
- Quoted reply should include:
  - sender name
  - short excerpt (truncate)
  - jump-to-original on click
- Avoid deep nesting in the main timeline; collapse multi-level context.

### Reactions
- Reactions are lightweight acknowledgment; keep them visually subordinate to content.
- Allow keyboard selection for accessibility if reactions are core to product.

## 5) Feedback for latency and streaming

### The UX contract
- **Immediate local echo**: show the user’s message instantly (optimistic UI), then reconcile with server id/status.
- **Clear delivery states**:
  - sending (spinner)
  - sent (no marker or subtle)
  - failed (explicit retry)
- If responses stream (LLM-style):
  - render progressively
  - provide **Stop generating**
  - allow **Regenerate** with preserved user message
  - avoid scroll-jitter while tokens arrive (see “stick to bottom” rule)

### Typing indicators
- Use sparingly; they help only when there is noticeable latency.
- Prefer deterministic progress (streaming) over ambiguous “typing…” when possible.

## 6) Content rendering rules (robustness beats cleverness)

### Text
- Respect user-entered newlines.
- Handle extremely long tokens (URLs, hashes) with:
  - `overflow-wrap: anywhere;`
  - optional “copy” affordance for long code/ids

### Markdown / rich blocks
- If you render Markdown:
  - sanitize strictly (XSS)
  - style code blocks, lists, tables conservatively
  - provide copy buttons for code blocks
- Distinguish “assistant authored” rich text from “user authored” rich text if security requires it.

### Media
- Images: lazy-load; show blurred placeholder; click-to-zoom; preserve aspect ratio to avoid layout jumps.
- Audio/video: inline controls; avoid auto-play; respect reduced motion/data saver settings.

## 7) Error states and trust

### Network/offline
- Offline banner with actionable state (“Reconnecting…”).
- Queue sends while offline only if you can guarantee ordering and reconciliation.
- For failed sends:
  - keep the message in place
  - show retry and “edit then resend”
  - don’t silently drop

### Moderation and safety affordances (if applicable)
- Reporting should be available but unobtrusive.
- If content is blocked/removed, show a clear placeholder explaining what happened (without leaking sensitive rules).

## 8) Performance fundamentals (frontend)

### Rendering strategy
- Chat timelines grow without bound. Use:
  - windowing/virtualization for long histories
  - incremental loading (paginate backwards)
  - stable keys (server ids)
- Avoid expensive re-renders on token streaming:
  - isolate the streaming message component
  - memoize message list items
  - throttle layout measurements

### Images and layout stability
- Reserve space for media using known dimensions to prevent reflow.
- Prefer CSS containment where appropriate.

### Scroll anchoring
- Preserve scroll position when prepending older messages.
- Measure the height delta and adjust scrollTop accordingly, rather than letting the browser jump.

## 9) Accessibility (non-negotiable)

### Semantics
- Treat the transcript as a log:
  - `role="log"` + `aria-live="polite"` for incoming messages (careful: too chatty is bad)
  - provide a “Pause announcements” toggle for heavy traffic
- Each message should be focusable and have an accessible name (sender + time + excerpt).

Example skeleton:
```html
<section role="log" aria-live="polite" aria-relevant="additions">
  <article tabindex="0" aria-label="Alex, 10:42, Hey are you free later?">
    <!-- message bubble -->
  </article>
</section>
```

### Keyboard UX
- Full keyboard path:
  - focus composer
  - navigate messages (Up/Down)
  - open message actions (Enter/Space)
  - escape closes menus/modals
- Visible focus rings, always.

### Motion and contrast
- Respect `prefers-reduced-motion`.
- Ensure contrast for bubble text, timestamps, icons, error states.

## 10) Internationalization and typography

- Support RTL (layout mirroring, punctuation handling).
- Date/time formats localize; avoid hard-coded strings (“Yesterday” needs locale rules).
- Handle long names and CJK text without breaking layout.

## 11) Product-level affordances that feel “modern”
- “Jump to bottom” button when scrolled up.
- Message search with in-context navigation (next/prev match).
- Pin/star important messages.
- Quick-reply chips for onboarding or common actions (but do not block freeform input).
- Theme toggle (light/dark) with system preference support.

## 12) A practical checklist (ship-ready)

**Transcript**
- [ ] Grouping + timestamps are readable and not noisy
- [ ] Auto-scroll only when “stick to bottom” is true
- [ ] New messages indicator appears when scrolled up
- [ ] Virtualization for long histories
- [ ] Robust rendering for long tokens, media, code blocks

**Composer**
- [ ] Draft persistence per conversation
- [ ] Multiline input with predictable send behavior
- [ ] Attachments: preview, progress, cancel, retry
- [ ] Optimistic send + clear failure recovery

**Reliability**
- [ ] Offline/reconnect states
- [ ] Idempotent send + reconciliation (no duplicates)
- [ ] Error copy is actionable

**A11y**
- [ ] Log semantics + sane live announcements
- [ ] Full keyboard support, visible focus
- [ ] Reduced motion, high contrast

**Security**
- [ ] Sanitized rich text/Markdown
- [ ] Safe link handling (rel, target), preview isolation
- [ ] No HTML injection via user content

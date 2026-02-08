---
name: add-fastapi-chat-ui
description: Add a lightweight browser UI to a FastAPI chatbot so developers can test conversations quickly without curl. Use when a project has `/chat` and `/chat/stream` endpoints but no frontend, or when you need a local QA harness showing runtime metadata, court-style spotlight tutorial overlays, per-node reasoning updates from LangGraph, transcript, and status output.
---

# Add FastAPI Chat UI

## Overview

Add a static, single-page test console for FastAPI chatbots.
Expose runtime metadata, send streamed turns, inspect per-node reasoning/status, and iterate quickly.
Apply the baseline patterns from `references/ui_tips.md` when implementing or revising UI behavior.

## UI Requirements

Include these sections in the page:

- Runtime info:
  show model, checkpointer mode, domain config path, tutorial config path.
- Conversation controls:
  thread ID input, message input, send action.
- Quick actions:
  buttons for common tutorial/testing commands (`help`, `next`, `skip`, etc.).
- Tutorial overlay:
  spotlight-style guided tour anchored to `data-tutorial-id` targets (court-style walkthrough).
- Reasoning feed:
  display graph-node updates per turn, grouped under the assistant reply for that same turn.
- Transcript:
  separate user/assistant/reasoning turns with timestamps.
- Status inspector:
  render the returned `status` object in a readable JSON panel.
- Error panel:
  clear request failures and backend error messages.
- Navbar auth controls:
  include compact registration/login controls on the left side of the top navbar, wired to backend auth/session APIs.
  include an explicit guest control and current auth/session indicator.

Prioritize conversation usability:

- The assistant conversation transcript must be the primary surface.
- Debug/engineering panes (reasoning feed, status JSON, endpoint toggles) should be secondary and collapsible by default.
- Sending a message should require minimal setup (defaults should work without touching advanced controls).
- Keep reasoning UX distinct from generic tools:
  reasoning should live with each turn (toggleable per-turn details), not only in global debug panes.

Minimum implementation details (from `references/ui_tips.md`):

- Transcript semantics:
  `role="log"`, `aria-live="polite"`, focusable message items with meaningful `aria-label`.
- Scroll contract:
  explicit stick-to-bottom state, auto-scroll only when sticky, and a visible jump/new-messages control when user is scrolled up.
- Composer behavior:
  auto-resize textarea, Enter to send with Shift+Enter newline, draft persistence keyed by thread id.
- Streaming controls:
  optimistic local echo, delivery state hints, and `Stop generating` while stream is active.
- Reasoning attention pattern:
  while waiting for the assistant, show an explicit thinking state with a spinner and node flashes directly in the pending assistant slot under the user message.
- Per-turn reasoning disclosure:
  each assistant turn should contain a collapsible reasoning history for that turn, with node updates separated and labeled by timestamp.
  once the final assistant message is rendered, hide the temporary live reasoning chip; users can still inspect reasoning via this per-turn collapsible section.
- Live reasoning behavior:
  update the pending assistant chip immediately with the latest available reasoning/status event (latest-wins), instead of replaying queued backlog.
  if backend supports partial reasoning events, live chip should update on partial text (`reasoning_generated_live`) in real time.
- Reasoning flash emphasis:
  make the live reasoning chip visually prominent (larger chip + stronger flash) so users can track node updates at a glance.
- Live reasoning readability:
  keep the live reasoning chip fixed-height and render the full reasoning text inside the box.
  render live reasoning with the same safe markdown renderer used for per-turn reasoning.
  size the live body with `box-sizing: border-box` so bottom padding is visible and text does not get clipped under overlays.
  drive scrolling from incoming chunks: on each live update, detect whether text spills below the readable zone (above the fade margin) and scroll just enough to keep it readable.
  compute overflow from the actual `scrollHeight` (do not subtract bottom padding from content height), otherwise scrolling can fail to trigger.
  for reliable motion, use spill-following on each chunk (`scrollTop += overflow`) rather than tiny fixed nudges that may never move the first line out of view.
  note: padding does not create scroll range (`scrollHeight` and `clientHeight` both include padding). if you need guaranteed room for bottom-guard scrolling, add an in-flow scroll buffer (for example `.thinking-live-body::after`) and subtract that buffer when computing content-bottom target.
  an even safer default is growth-following: track last rendered `scrollHeight` per turn and increment `scrollTop` by positive height delta each chunk; this guarantees visible movement when rendered text grows.
  avoid relying on `height: 100%` for the live box when the parent only has min/max height; make the live box an explicit fill container (`position:absolute; inset:0`) so it is a true scroll container.
  for a new reasoning summary block, reset to top first, then continue chunk-by-chunk overflow scrolling.
  if the model interleaves multiple live summary streams (`summary_index` values), keep the live chip pinned to the newest summary index and ignore older-index deltas to avoid repeated top resets.
  reserve enough bottom padding in the live box so the last line never sits under the fade margin.
  preserve autoscroll progress across live re-renders so incoming chunks do not snap the viewport back to the top.
  when stream payloads include `summary_index`, reset the live viewport only when the summary index changes (new reasoning block), not on ordinary text deltas.
  include a subtle in-box scroll cue/progress indicator so the auto-scroll behavior is visually obvious.
  before generated model reasoning arrives, keep the chip visibly active with lightweight heartbeat copy (for example, periodic "Thinking..." updates) so users are not left with a static near-empty box.
  keep spinner and live chip in separate layout columns so live updates do not visually overlap the loading indicator.
- Reasoning category split:
  treat node/status updates and model-generated reasoning as separate event categories.
  if deterministic logic explanations are emitted (rule-based or non-LLM decisions), keep them as a third category.
  recommended stream event types: `reasoning_generated_live`, `reasoning_generated`, `reasoning_deterministic`, `reasoning_status`.
- Reasoning display mode:
  provide a clear selector with at least `both` (generated + status), `both + deterministic`, `generated only`, `deterministic only`, `status only`, and `off`, applied consistently to both the live thinking slot and per-turn reasoning history.
  in `both` mode, keep generated reasoning as the live chip priority so status updates do not eclipse model reasoning.
- Reasoning cadence control:
  provide a configurable minimum interval for live reasoning chip updates (default `300ms`) to avoid unreadable rapid bursts.
- Robust rendering:
  preserve newlines and hard-wrap long tokens (`overflow-wrap: anywhere;`).
- Markdown rendering:
  render assistant content and per-turn reasoning history as safe markdown (paragraphs/lists/inline code/code fences/links), while keeping user drafts plain text.
- Conversation-first default:
  keep transcript + composer prominent, with advanced diagnostics tucked into a secondary panel users can open when needed.
  place the `Tools` toggle in the top navbar (not floating lower on the page), and constrain the tools panel with both `top` and `bottom` so it always fits within the viewport.
- Auth + guest defaults:
  default session should start as guest on page load.
  if guest code can come from both query string (`GET`) and JSON body (`POST`), `POST` must take precedence.
  registration/login actions should switch active thread id to the returned authenticated session.
- Branding variables:
  keep UI title and assistant display name configurable via runtime metadata (for example `ui_title`, `assistant_name`) instead of hard-coded strings.

## Workflow

1. Add backend metadata + tutorial routes
- Add `GET /meta` that returns runtime values needed by the UI.
- Include at least `model`, `checkpointer`, `domain_path`, `tutorial_path`, and app title/version.
- Add `GET /tutorial` that returns enabled flag + step list for overlay walkthrough.
- Add auth/session routes used by the navbar controls:
  `POST /auth/register`, `POST /auth/login`, and guest session route(s) (`GET/POST /auth/guest`).

2. Add static UI files
- Copy `assets/simple-chat-ui/index.html` into the app package (for example `<package>/ui/index.html`).
- Keep it dependency-free (vanilla HTML/CSS/JS) unless the host project already uses a frontend framework.

3. Serve the UI from FastAPI
- Mount static files at `/ui`.
- Redirect `/` to `/ui/` for easy opening.
- Keep API endpoints unchanged.

4. Wire request flow to the graph stream
- Default UI calls to `POST /chat/stream`.
- Stream and render reasoning events per node (e.g. `ingest`, `analyze`, `act`, `compose`).
- Prefer explicit event types so the UI can separate reasoning categories:
  `reasoning_generated` (LLM summaries), `reasoning_deterministic` (rule-based explanations), and `reasoning_status` (node status updates).
- If available, stream partial LLM reasoning with `reasoning_generated_live`.
- Emit a user-friendly status update as soon as long-running nodes start so users see activity immediately.
- Stream and render final assistant message + status payload.
- Keep a non-stream fallback path to `POST /chat`.

5. Implement tutorial overlay behavior
- Auto-open the overlay on first visit unless dismissed in localStorage.
- Include `Back`, `Next`, `Finish`, and `Don't show again`.
- Spotlight the current step target and scroll it into view when possible.

6. Validate
- Open `/ui/` and confirm tutorial overlay anchors to the right targets.
- Send a streamed turn and confirm reasoning updates appear per graph node.
- Confirm reasoning affordance:
  node flashes appear in the pending assistant slot while thinking, and completed turns expose toggleable per-turn reasoning history.
- Confirm reasoning pacing + mode:
  only one live reasoning pop is visible at a time, it always reflects the latest available event, and switching reasoning display mode (`both/both+deterministic/generated/deterministic/status/off`) updates both the live slot and per-turn history visibility.
- Confirm final assistant message + status render and `/threads/{id}/status` refresh works.
- Confirm scroll behavior:
  when scrolled up, new content does not snap the view and jump control appears.
- Confirm draft behavior:
  switching thread id restores per-thread draft text.
- Confirm accessibility:
  transcript has log semantics and keyboard focus can reach individual messages.

## Assets

- `assets/simple-chat-ui/index.html`:
  base page template for the FastAPI chat test console.

## References

- `references/ui_tips.md`:
  modern chat UI/UX implementation guidance and ship checklist.

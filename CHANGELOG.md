# CHANGELOG

All notable changes to this repository are documented in this file.

## 2026-03-10 (Gateway API Key Resolution + CI Test Isolation)

### Summary

Made gateway API-key resolution explicit at request time so missing server credentials return deterministic route errors, and hardened gateway tests to patch the API-key helper instead of patching internal module state.

### Backend

- Updated `backend/gateway/app.py`:
  - replaced module-import API key capture with `_gateway_api_key()`
  - missing API key now returns `500` JSON for `POST /api/chat`
  - missing API key now emits SSE `error` then `done(error)` for `POST /api/chat/stream`

### Tests

- Updated `tests/test_gateway_app.py`:
  - patch `_gateway_api_key()` instead of `_API_KEY`
  - duplicate `request_id` tests no longer depend on ambient env state
  - added explicit missing-API-key coverage for both chat and stream routes

### Docs

- Updated `docs/assistant/api-and-sse-contract.md`
- Updated `README.md`

## 2026-03-10 (Stream Init Error Handling + Active Request ID Guard + Empty Model Selector)

### Summary

Hardened stream startup failure handling, rejected duplicate active top-level `request_id` reuse, and made the frontend model selector degrade safely when capabilities expose no selectable models.

### Backend

- Updated `backend/application/chat_use_cases.py`:
  - moved stream client construction inside the worker `try` block so setup failures still emit `error` then `done(error)`
  - ensure setup-time failures still clean up the execution registry and close the sink
- Updated `backend/domain/execution.py`:
  - added `DuplicateRequestIdError`
  - reject duplicate active top-level `request_id` registration instead of overwriting the previous execution
- Updated `backend/gateway/app.py`:
  - `POST /api/chat` now returns `409` with `error: "request_id already active"` for duplicate active request ids
  - `POST /api/chat/stream` preserves the SSE contract and emits `error` then `done(error)` for the same condition

### Frontend

- Updated `frontend-react/src/components/ModelSelect.jsx`:
  - disable the trigger and show `No models available` when capabilities return an empty model list
  - guard keyboard handlers and menu opening so empty model lists cannot enter an invalid focus/index state

### Tests

- Updated `tests/test_execution.py` with duplicate active `request_id` rejection and post-finish reuse coverage
- Updated `tests/test_chat_use_cases.py` with stream init failure cleanup coverage
- Updated `tests/test_gateway_app.py` with duplicate active `request_id` behavior for both chat and stream routes
- Updated `frontend-react/src/__tests__/ModelSelect.test.jsx` with empty-model-list coverage

### Docs

- Updated `docs/assistant/api-and-sse-contract.md`
- Updated `docs/assistant/validation-and-release-checklist.md`
- Updated `README.md`

## 2026-03-10 (OpenAI Responses Timeout + Multi-item Hardening)

### Summary

Hardened the OpenAI Responses protocol path so transport timeouts now preserve the backend timeout flow, and lifecycle fallback is more robust when the proxy emits multiple `response.output_item.added` snapshots for the same item.

### Backend

- Updated `backend/infrastructure/protocols/openai_responses.py`:
  - switched OpenAI `/responses` streaming transport to `httpx` with a dedicated SSE read-idle timeout
  - preserve OpenAI read/connect timeout failures as `TimeoutError` instead of normalizing them into generic upstream runtime errors
  - merge repeated `response.output_item.added` / `response.output_item.done` snapshots by item identity
  - keep fallback ordering stable by `output_index` or first-seen order when `output_index` is absent
  - replay snapshot-based stream fallback incrementally so repeated item snapshots do not duplicate already-emitted text
- Updated `backend/infrastructure/provider_settings.py`:
  - added `OPENAI_SSE_READ_TIMEOUT_SECONDS` resolution with default `600`

### Tests

- Updated `tests/test_proxy_chat_model.py` with coverage for repeated `output_item.added` merges, `added -> done` tool-call recovery, first-seen ordering without `output_index`, incremental snapshot replay, and OpenAI timeout propagation as `TimeoutError`
- Updated `tests/test_provider_settings.py` for `OPENAI_SSE_READ_TIMEOUT_SECONDS`

### Docs

- Updated `docs/assistant/runtime-and-commands.md`
- Updated `docs/assistant/model-and-provider-policy.md`
- Updated `README.md`
- Updated `.env.example`

## 2026-03-10 (Local Ctrl+C Graceful Stream Shutdown)

### Summary

Changed the local `python server.py` shutdown path so the first `Ctrl+C` now drains active streaming requests instead of exiting immediately.

### Backend

- Updated `backend/domain/execution.py`:
  - track active executions by kind (`stream` vs `once`)
  - added stream-only batch cancellation and bounded drain waiting helpers
  - kept duplicate `request_id` finish semantics precise by matching the current token
- Updated `backend/application/chat_use_cases.py` to register `chat_once` as `once` and `stream_chat` as `stream`
- Updated `backend/nvidia_client.py` with `cancel_active_streams_for_shutdown(timeout_seconds)` as the shutdown-facing facade helper
- Updated `backend/gateway/app.py`:
  - added a local shutdown gate for `/api/chat` and `/api/chat/stream`
  - kept `/api/chat/cancel` available during shutdown drain
- Updated `backend/server.py`:
  - replaced the direct `uvicorn.run(...)` call with a local graceful-shutdown wrapper
  - first `Ctrl+C` now flips shutdown mode, cancels active streams, waits up to `SHUTDOWN_CANCEL_DRAIN_SECONDS`, then exits
  - second `Ctrl+C` still force-exits immediately

### Tests

- Updated `tests/test_execution.py`
- Updated `tests/test_gateway_app.py`
- Added `tests/test_server.py`

### Docs

- Updated `docs/assistant/api-and-sse-contract.md`
- Updated `docs/assistant/architecture-rules.md`
- Updated `docs/assistant/runtime-and-commands.md`
- Updated `README.md`
- Updated `.env.example`

---

## 2026-03-09 (Responsive Session Drawer On Narrow Desktop)

### Summary

Extended the frontend session sidebar responsiveness so narrow desktop widths now collapse into the same overlay drawer pattern already used on mobile, without forcing the rest of the chat layout into mobile spacing.

### Frontend

- Updated the React app shell/session sidebar layout logic:
  - measure shell width and rendered sidebar width with `ResizeObserver`
  - switch to overlay mode when `appShellWidth <= sessionSidebarWidth * 2.7`
  - keep the chat pane in desktop layout while only collapsing the session rail
  - reuse the existing header-triggered drawer interactions for both true mobile and narrow desktop
  - reduce the chat card outer radius while narrow-desktop overlay mode is active so the panel matches the tighter layout before full mobile styles take over

### Tests

- Updated `frontend-react/src/__tests__/SessionSidebar.test.jsx`
- Updated `frontend-react/src/__tests__/App.behavior.test.jsx`
- added coverage for overlay auto-close behavior, backdrop gating, narrow-width activation, and widening back out of overlay mode

### Docs

- Updated `docs/assistant/architecture-rules.md`
- Updated `docs/assistant/validation-and-release-checklist.md`
- Updated `README.md`

---

## 2026-03-10 (OpenAI Responses Lifecycle Compatibility)

### Summary

Hardened OpenAI Responses handling so both invoke and stream paths can reconstruct results from the lifecycle `response.created -> response.output_item.added/done -> response.completed`, while still preferring `response.completed` when present.

### Backend

- Updated `backend/infrastructure/protocols/openai_responses.py`:
  - added a small lifecycle accumulator for `response.created`, `response.output_item.added`, `response.output_item.done`, and optional `response.completed`
  - prefer `response.completed.response` over output-item snapshots, and prefer `output_item.done` over `output_item.added`
  - finalize from EOF item snapshots only when no `response.completed` is received and recoverable output items exist
  - keep stream text de-duplicated when both deltas and final output snapshots are present

### Tests

- Updated `tests/test_proxy_chat_model.py` with coverage for lifecycle ordering, EOF fallback, tool-call reconstruction, and stream no-duplication

### Docs

- Updated `docs/assistant/model-and-provider-policy.md`

---

## 2026-03-10 (Claude Messages Lifecycle Tool-Use Compatibility)

### Summary

Hardened Anthropic Messages handling so Claude lifecycle streams can recover text and tool-use state across `message_start`, `content_block_*`, `message_delta`, and `message_stop` without changing the frontend SSE contract.

### Backend

- Updated `backend/infrastructure/protocols/anthropic_messages.py`:
  - added a Claude lifecycle accumulator for message/content-block events
  - parse invoke content blocks through the same block parser used by lifecycle recovery
  - keep `stream()` outward semantics unchanged while allowing EOF text recovery from completed lifecycle state
  - reconstruct `tool_use` only when accumulated `input_json_delta` is complete and parseable

### Tests

- Updated `tests/test_proxy_chat_model.py` with coverage for Anthropic reasoning/tool-use parsing, EOF text recovery, and incomplete tool JSON behavior

### Docs

- Updated `docs/assistant/model-and-provider-policy.md`

---

## 2026-03-09 (Add NVIDIA Qwen 3.5 122B A10B Model)

### Summary

Added NVIDIA catalog support for `qwen/qwen3.5-122b-a10b`, including its reasoning/agent metadata and backend test coverage.

### Backend

- Updated `backend/domain/model_templates.py`:
  - added `qwen/qwen3.5-122b-a10b`
  - configured call-time thinking control via `chat_template_kwargs.enable_thinking`
  - kept media input disabled so the model stays aligned with the current agent-first routing
  - registered the same NVIDIA agent configuration used by the other agent-ready models

### Tests

- Updated `tests/test_model_registry.py`
- Updated `tests/test_model_profile.py`
- Updated `tests/test_nvidia_client.py`

### Docs

- Updated `README.md`
- Updated `docs/assistant/model-and-provider-policy.md`
- Updated `.env.example`
- Documented that pinned `*_MODELS` env vars are allowlists and must include newly added models

---

## 2026-03-09 (Session Delete Hover Reveal)

### Summary

Adjusted the session delete affordance so it stays visually quieter in the sidebar: on pointer-hover devices the delete chip now appears only when a session card is hovered or keyboard-focused, while running sessions still keep deletion disabled.

### Frontend

- Updated `frontend-react/src/styles.css`:
  - session delete control now hides by default on hover-capable devices
  - reveals on `.session-row:hover` and `.session-row:focus-within` to preserve keyboard access
  - touch devices keep the delete control visible so mobile deletion remains available

### Docs

- Updated `README.md` and `docs/assistant/validation-and-release-checklist.md` to reflect the new delete-button visibility behavior

---

## 2026-03-06 (Web Loader: httpx async + trafilatura)

### Summary

Replaced LangChain `WebBaseLoader` with `httpx.AsyncClient` (async concurrent fetching, HTTP/2, connection pooling) and `trafilatura` (professional article text extraction). Significantly improves reliability for Chinese sites and other slow endpoints.

### Backend

- **`backend/web_search.py`**: Rewrote page loading pipeline:
  - Async concurrent fetching via `httpx.AsyncClient` with `asyncio.Semaphore` concurrency control
  - `trafilatura.extract()` for clean article text extraction (falls back to `bs4` if unavailable)
  - Browser-level `User-Agent` header for better compatibility
  - SSL verification fallback (retries with `verify=False` on cert errors)
  - Increased default timeouts: per-page read 10s (was 2s), total budget 15s (was 4s), connect 5s (new)
  - Sync wrapper (`_load_pages_sync`) handles both async and sync calling contexts
  - `load_webpage_content()` signature unchanged for backward compatibility
- **`requirements.txt`**: Added `httpx>=0.27,<1` and `trafilatura>=2.0,<3`

### Tests

- Updated `tests/test_web_search.py`: Adapted mocks for new httpx/trafilatura pipeline, added extraction fallback tests and async loader test

---

## 2026-03-06 (Launch Risk Hardening Follow-up)

### Summary

Closed the highest-risk backend follow-ups from the FastAPI refactor: request cancellation now survives duplicate `request_id` reuse correctly, gateway request parsing is stricter at the boundary, provider timeout configuration is provider-aware, and search orchestration is routed through `SearchService` instead of being reassembled inside use cases.

### Backend

- Hardened `backend/domain/execution.py`:
  - `CancellationRegistry.finish()` now removes only the matching token for the active request mapping
  - duplicate `request_id` reuse no longer lets an older request clear a newer request's cancellation handle
- Tightened `backend/gateway/app.py` request parsing:
  - `Content-Length` is checked before reading request bodies
  - request parsing now uses dedicated gateway exceptions instead of generic runtime exceptions
  - `request_id` now has a `256` character limit for chat and cancel routes
- Updated `backend/schemas.py` to enforce the same `request_id` length ceiling at schema level.
- Updated provider configuration handling:
  - `backend/infrastructure/provider_settings.py` now resolves timeout via `<PROVIDER>_TIMEOUT_SECONDS` -> `MODEL_TIMEOUT_SECONDS` -> default `300`
  - disabled `<PROVIDER>_SSL_VERIFY=false` now emits a warning log
  - `backend/settings/env_loader.py` now avoids re-reading the same `.env` root repeatedly
- Updated `backend/infrastructure/chat_model_factory.py` to use provider-aware timeout resolution.
- Routed search orchestration through `backend/application/search_service.py` from `backend/application/chat_use_cases.py` for both one-shot and stream flows.
- Hardened `backend/event_mapper.py` so provider stream `close()` failures no longer overwrite the original upstream failure.
- Added lock protection around active catalog initialization in `backend/domain/model_catalog.py`.

### Documentation

- Updated `README.md`
- Updated `docs/assistant/api-and-sse-contract.md`
- Updated `docs/assistant/runtime-and-commands.md`
- Updated `docs/assistant/architecture-rules.md`
- Updated `docs/assistant/model-and-provider-policy.md`
- Updated `docs/assistant/path-index.md`

### Validation

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` passed (255 tests)

## 2026-03-06 (FastAPI Gateway Refactor + Cancel Endpoint + Analytics)

### Summary

Refactored the backend around a FastAPI gateway and split the old aggregated backend flow into gateway, application, domain, and infrastructure layers. Added a dedicated cancel endpoint so the existing `Stop` control can signal backend cancellation before aborting the local SSE transport. Also integrated Vercel Analytics on the React frontend.

### Backend

- Added `backend/gateway/app.py` as the FastAPI entrypoint for:
  - `GET /api/capabilities`
  - `POST /api/chat`
  - `POST /api/chat/stream`
  - `POST /api/chat/cancel`
- Added `backend/gateway/admission.py` for gateway concurrency limits, bounded queueing, and queue timeout control via:
  - `GATEWAY_MAX_CONCURRENCY`
  - `GATEWAY_MAX_QUEUE_SIZE`
  - `GATEWAY_QUEUE_TIMEOUT_SECONDS`
- Restored path traversal protection for FastAPI static file serving and tightened tests around the gateway route.
- Split configuration/model concerns:
  - added `backend/settings/env_loader.py`
  - added `backend/infrastructure/provider_settings.py`
  - added `backend/domain/model_templates.py`
  - added `backend/domain/model_catalog.py`
- Added execution primitives and use cases:
  - `backend/domain/execution.py`
  - `backend/application/chat_use_cases.py`
  - `backend/application/agent_session_builder.py`
  - `backend/application/search_service.py`
- Refactored provider plumbing:
  - `backend/proxy_chat_model.py` is now a thin adapter
  - provider-specific request/stream handling moved under `backend/infrastructure/protocols/*`
  - shared HTTP/SSE transport moved under `backend/infrastructure/transport/*`
- Kept `backend/nvidia_client.py` as the public facade while delegating runtime orchestration to use cases.
- Added backend cancellation registry and `cancel_chat(request_id)` facade.
- Simplified cancel terminal-event delivery so `done(stop)` can pass through the event sink instead of relying only on downstream synthesis.
- Switched local server runtime to `uvicorn` via `backend/server.py`.
- Added ASGI Vercel wrappers for the FastAPI app, including `api/chat/cancel.py`.

### Frontend

- Added `cancelChat()` in `frontend-react/src/shared/api/chatApiClient.js`.
- Updated `useStreamController` so `Stop` first calls `/api/chat/cancel` and then aborts the local fetch.
- Added Vercel Analytics with `@vercel/analytics/react` in `frontend-react/src/main.jsx`.

### Documentation

- Updated `README.md`
- Updated `docs/assistant/api-and-sse-contract.md`
- Updated `docs/assistant/architecture-rules.md`
- Updated `docs/assistant/runtime-and-commands.md`
- Updated `CLAUDE.md`

### Validation

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` passed (230 tests)
- `pnpm test` passed in `frontend-react`
- `pnpm run build` passed in `frontend-react`

## 2026-03-06 (Per-Provider SSL Verification Control)

### Summary

Added per-provider SSL certificate verification control via environment variables, enabling routing through third-party API proxies that have hostname-mismatched or self-signed certificates.

### Backend

- **`backend/config.py`**: Added `provider_ssl_verify(provider)` function reading `<PROVIDER>_SSL_VERIFY` env var (accepts `false`, `0`, `no`; defaults to `true`).
- **`backend/proxy_chat_model.py`**:
  - Added `ssl_verify` field to `ProxyGatewayChatModel`
  - Added `_make_ssl_context()` helper returning an unverified SSL context when `ssl_verify=False`
  - Added `_urlopen()` instance method for SSL-aware HTTP requests
  - Updated `_json_post()` to accept `ssl_verify` parameter
  - All HTTP call sites (invoke + stream for Anthropic, OpenAI, Google) now respect `ssl_verify`
- **`backend/model_profile.py`**: All `ProxyGatewayChatModel` construction paths now pass `ssl_verify=provider_ssl_verify(provider)`.

### Configuration

- New env variables: `ANTHROPIC_SSL_VERIFY`, `OPENAI_SSL_VERIFY`, `GOOGLE_SSL_VERIFY` (default `true`)

### Documentation

- Updated `docs/assistant/model-and-provider-policy.md` with SSL verification note
- Updated `README.md` with SSL verification env variables

### Validation

- `python -m unittest discover -s tests -v` passed (210 tests)

## 2026-03-05 (Session Sidebar Fixed-Responsive Width + Mobile Drawer)

### Summary

Adjusted session sidebar layout to keep a stable responsive width on non-mobile screens, fixed internal text column width for title/preview, and switched mobile behavior to a left drawer opened from the chat header.

### Frontend

- Sidebar layout:
  - replaced content-driven sidebar sizing with responsive fixed width tokens
  - desktop/tablet keeps two-column layout (`sidebar + chat`) without mid-breakpoint stacking
- Session item internals:
  - title/preview text area now uses fixed column width for stable truncation and alignment
  - time column stays independent on the right
- Mobile drawer UX:
  - added chat-header `Sessions` trigger (`aria-controls` + `aria-expanded`)
  - session sidebar becomes a left overlay drawer on `<=600px`
  - selecting session / creating new chat / clicking backdrop closes drawer on mobile

### Tests

- Added `frontend-react/src/__tests__/SessionSidebar.test.jsx`:
  - mobile auto-close after session select and new chat
  - desktop no auto-close
  - backdrop closes sidebar
- Updated `frontend-react/src/__tests__/App.behavior.test.jsx`:
  - header sessions button opens sidebar and updates accessibility state
- Updated `frontend-react/src/__tests__/SessionList.test.jsx`:
  - fixed text-column rendering sanity for long title/preview

## 2026-03-05 (Proxy Stream Error Type Preservation)

### Summary

Fixed provider stream error normalization so SSE `error` frames preserve upstream error type metadata (for example `type=request_error`) instead of degrading to `type=unknown_error`.

### Backend

- Added `_detail_from_stream_error_event(...)` in `backend/proxy_chat_model.py`.
- Updated Anthropic/OpenAI/Google stream error branches to raise normalized detail directly from provider SSE payloads.
- Updated OpenAI invoke-path SSE `error` handling to preserve upstream `error.type` as well.

### Tests

- Updated `tests/test_proxy_chat_model.py`:
  - strengthened `test_openai_stream_event_error_is_normalized` with `type=request_error` assertion
  - added `test_openai_invoke_event_error_is_normalized`

### Validation

- `.\.venv\Scripts\python.exe -m unittest tests.test_proxy_chat_model tests.test_chat_handlers -v` passed (67 tests).

## 2026-03-05 (Reasoning Stream Readability + Multi-turn Visibility)

### Summary

Fixed reasoning stream rendering readability and improved same-session multi-turn visibility by auto-expanding the current round while folding historical rounds.

### Frontend

- **Reasoning chunk merge readability**:
  - `mapStreamEventToPatch` now uses `mergeReasoningChunk(prev, next)` instead of raw concatenation
  - adds safe spacing for merged alphanumeric boundaries (prevents `ratiosPlanning` style concatenation)
  - adds `agent_step_start`-driven paragraph breaks so new agent steps render on separate lines
  - adds paragraph splitting for step-like reasoning chunks (capitalized multi-word chunk boundaries)
  - adds in-chunk sticky split fallback (`...stepsPlanning...`, `...limitations****Confirming...`)
  - inserts paragraph breaks before markdown block starts like `****`, headings, and list prefixes when needed
  - preserves incoming leading whitespace/punctuation behavior
  - does not force spacing for CJK chunk boundaries
- **Reasoning visibility policy**:
  - `MessageList` now marks the focused request (active request, or latest stream round fallback)
  - `StreamMessage` reasoning panel defaults to open for focused/current round and defaults to folded for historical rounds
  - reasoning section remount key includes current/history state so previous round folds automatically when a new round starts
- **Visual tuning**:
  - reasoning body text now uses a muted gray tone to reduce visual noise

### Tests

- Updated `mapStreamEventToPatch.test.js` with chunk-merge readability coverage:
  - alphanumeric seam spacing
  - step-event boundary split (`agent_step_start -> reasoning`)
  - duplicate-step no-extra-break guard
  - in-chunk sticky step/markdown split
  - markdown block paragraph breaks
  - existing whitespace preservation
  - CJK no-forced-space case
- Updated `MessageList.test.jsx` and `StreamMessage.test.jsx` for current vs historical reasoning panel behavior
- Updated `App.behavior.test.jsx` with same-session two-turn reasoning visibility integration case

## 2026-03-05 (Composer Stop Toggle + Session Delete Placement + Final Context Usage)

### Summary

Implemented UX and stream-contract follow-ups: moved stop control into the composer send button state, stabilized session delete placement, simplified chat header height/content, and added terminal context-usage refresh (`phase=final`) before normal stream completion.

### Frontend

- **Composer stop/send toggle**:
  - removed status-bar stop button
  - composer submit button now switches to `Stop` state (outer circle, inner square) only for the active running session
  - when another session is running, input/send remain disabled (global single in-flight policy unchanged)
- **Session delete action**:
  - moved delete control to session card bottom-right
  - removed hover-only hidden behavior; control is always visible
  - running sessions remain non-deletable (`disabled`) with existing data-layer guard preserved
- **Header simplification**:
  - removed right-side feature pills/meta block
  - reduced header vertical density and copy length
- **Session UX polish**:
  - invalid `updatedAt` no longer renders `Invalid Date` tooltip
  - clearing session filter now applies immediately (no debounce delay)
- **Context usage rendering**:
  - `mapStreamEventToPatch` now replaces `usageLines` when receiving `context_usage` with `phase=final`

### Backend

- **Terminal context usage update**:
  - `stream_direct` now emits final `context_usage` before `done(stop)`, based on input messages + final visible answer
  - `stream_agentic` now emits final `context_usage` before `done(stop)`, based on input messages + collected token output
- Error flow invariant remains unchanged: `error` is still followed by `done(error)`.

### Tests

- Updated frontend tests:
  - `mapStreamEventToPatch.test.js` adds `phase=final` overwrite assertion
  - `SessionList.test.jsx` adds invalid-date tooltip guard
- Updated backend tests:
  - `test_nvidia_client.py` asserts a terminal `context_usage` event with `phase=final` for direct and agentic streams

## 2026-03-05 (Draft Session Switching Fix + Sidebar Card UI Refresh)

### Summary

Fixed new-chat switching behavior so draft mode no longer reuses previous session messages, and refreshed the session sidebar into a card-based information layout.

### Frontend

- **Draft session behavior (`NEW_SESSION_KEY`)**:
  - fixed query state transition so switching to draft view no longer shows stale previous-session data
  - `App` now treats `NEW_SESSION_KEY` as a hard draft branch and does not consume session detail data there
  - unsent draft text is preserved when switching to existing sessions and restored when returning to `+ New Chat`
  - first send from draft now clears the `NEW_SESSION_KEY` draft to prevent sent text from reappearing later
- **Session sidebar UI**:
  - added session header with workspace context and conversation count
  - upgraded search area (inline search label + clear action)
  - card-style session rows with top meta row, preview clamping, and `Active` / `Running` badges
  - delete action moved to floating secondary action with clearer hover/focus affordance
  - added stronger focus-visible styles for keyboard navigation
- **react-query lite optimization**:
  - `useQuery` now re-initializes local state when `queryKey` changes, including disabled-query branches
  - cache subscription now avoids redundant `setState` when value is unchanged

### Tests

- Added `frontend-react/src/__tests__/reactQueryLite.test.jsx`:
  - verifies key-switch state reset under `enabled=false`
- Expanded `frontend-react/src/__tests__/App.behavior.test.jsx`:
  - verifies draft switching semantics (`+ New Chat` hides old messages, preserves unsent draft, clears after first send)
- Updated `frontend-react/src/__tests__/SessionList.test.jsx`:
  - includes `Active` badge assertion for updated card layout semantics

### Validation

- `pnpm test` passed (58 tests)
- `pnpm run build` passed

## 2026-03-05 (Frontend UI Modernization Optimization Fixes)

### Summary

Implemented the frontend optimization follow-up for code review findings: reduced streaming-time rendering cost, simplified collapsible section state semantics, added Prism lazy loading, added mobile/fallback visual degradations for glass effects, and expanded test coverage.

### Frontend

- **RichBlock streaming/perf**:
  - code copy behavior now uses one delegated click listener per `RichBlock` container (no per-button attach/detach churn)
  - copy reset timers are tracked safely per button
  - Prism highlighting is skipped during `streaming=true` and runs after completion
  - only unhighlighted nodes are processed (`data-prism-highlighted`)
- **Prism lazy loading**:
  - removed eager `App.jsx` import of `prism-setup`
  - added `frontend-react/src/utils/prism-loader.js` with module-level singleton promise (`ensurePrismLoaded`)
  - Prism setup remains in `prism-setup.js`, now loaded on demand when code blocks exist
- **Markdown hardening/cleanup**:
  - removed deprecated `marked` options (`mangle`, `headerIds`)
  - normalized fenced code language IDs to `[a-z0-9_-]` and defaulted to `text`
- **CollapsibleSection simplification**:
  - removed `forceOpen` prop and sync effect
  - `Search` section now uses key-based remount by `search.state` and defaults to:
    - open while `loading`
    - collapsed on `done`/`error`
- **Styles**:
  - removed dead `.chat::after` highlight pseudo-element
  - merged top highlight into `.chat` inset shadow
  - added `@supports not (backdrop-filter: blur(1px))` fallback backgrounds
  - added mobile (`max-width: 760px`) blur reduction for assistant message/sections

### Tests

- Added `frontend-react/src/__tests__/RichBlock.test.jsx`
  - fenced code copy button rendering
  - delegated copy behavior and reset timing
  - skip highlight during stream + highlight after completion
  - Prism lazy-load path
- Added `frontend-react/src/__tests__/markdown.test.js`
  - fenced wrapper/chrome output
  - default language fallback to `text`
  - language info-string normalization
  - inline code path remains unwrapped
- Added `frontend-react/src/__tests__/StreamMessage.test.jsx`
  - search panel remount behavior from `loading -> done`
  - manual toggle persistence when state key is unchanged

### Documentation

- Updated `docs/assistant/architecture-rules.md` with the stream-time Prism rule.
- Updated `docs/assistant/validation-and-release-checklist.md` with code-block copy/highlight verification.
- Updated `README.md` to reflect code-block copy/highlight behavior.

## 2026-03-05 (Progressive Disclosure Docs Refactor: AGENTS + CLAUDE)

### Summary

Reorganized assistant-facing documentation into a 3-layer progressive disclosure structure with a shared single source of truth. Behavior contracts are unchanged.

### Documentation Structure

- Added shared L2/L3 documentation under `docs/assistant/`:
  - `runtime-and-commands.md`
  - `api-and-sse-contract.md`
  - `model-and-provider-policy.md`
  - `architecture-rules.md`
  - `path-index.md`
  - `validation-and-release-checklist.md`
- Converted `AGENTS.md` to a thin L1 entry page with hard constraints and navigation links.
- Converted `CLAUDE.md` to a thin L1 entry page with command quickstart, troubleshooting pointers, and navigation links.

### Contract and Behavior

- No runtime API behavior changed.
- No SSE event names changed.
- No model policy implementation changed.
- Existing invariants remain intact (including `error -> done(error)` sequence).

## 2026-03-04 (Frontend Stream Terminal Consistency + Race Hardening)

### Summary

Hardened frontend stream terminal handling to remove cleanup races and ensure only one terminal outcome is applied per request.

### Frontend

- **Await terminal callbacks**:
  - `useStreamController` now awaits `onTransportError` and `onAborted`
  - `chatApiClient.streamChat` now awaits `handlers.onDone`
- **Single terminal exit**:
  - `useSendMessage` introduces request-scoped `finalizeStreamOnce` with idempotent guard
  - terminal causes (`done`, transport error, aborted) converge through one path
  - first terminal signal wins, preventing `done`/abort/error overwrite races
- **Event handling cleanup**:
  - `onEvent` no longer finalizes on `done`; it records terminal error context and only applies incremental content updates

### Tests

- New unit tests: `frontend-react/src/__tests__/useStreamController.test.jsx`
  - verifies `onAborted` callback is awaited
  - verifies `onTransportError` callback is awaited
- Expanded behavior tests in `frontend-react/src/__tests__/App.behavior.test.jsx`
  - global single-stream blocking and explicit stop flow
  - `done + abort` race: first terminal outcome wins
  - `done + transport error` race: first terminal outcome wins

### Validation

- `pnpm test` passed
- `pnpm test:e2e` passed
- `pnpm run build` passed

## 2026-03-04 (Frontend Optimization: Performance, Robustness, UI Quality)

### Summary

Frontend optimization pass covering streaming performance, error resilience, UI improvements, and legacy code cleanup.

### Performance

- **MathJax debounce**: `RichBlock` now debounces `MathJax.typesetPromise()` by 500ms, avoiding expensive typesetting on every streaming token. (`frontend-react/src/components/RichBlock.jsx`)
- **Message memoization**: `UserMessage` and `AssistantMessage` extracted as `memo()` components in `MessageList`, preventing completed messages from re-rendering during streaming. (`frontend-react/src/components/MessageList.jsx`)
- **content-visibility**: Completed messages (`.msg.assistant:not(.stream)`, `.msg.stream-done`) use `content-visibility: auto` to skip off-screen rendering. (`frontend-react/src/styles.css`)

### Robustness

- **ErrorBoundary**: New `ErrorBoundary` class component wraps `<AppContent>` at top level and each `<RichBlock>` in `StreamMessage` per-message. Catches render crashes with retry button. (`frontend-react/src/components/ErrorBoundary.jsx`)
- **AbortController**: `streamChat()` now accepts an optional `signal` param. `useStreamController` creates and manages an `AbortController` per stream, aborting in-flight requests before starting new ones. (`frontend-react/src/shared/api/chatApiClient.js`, `frontend-react/src/features/chat/useStreamController.js`)
- **Send mutex**: `useSendMessage` uses a synchronous `sendingRef` mutex to prevent double-send race conditions between the Zustand state check and `startRequest()`. (`frontend-react/src/features/chat/useSendMessage.js`)
- **Stream retry**: `useStreamController` retries once (2s backoff) on network errors or 5xx status, but only when no tokens have been received yet — avoids duplicate answers/billing. (`frontend-react/src/features/chat/useStreamController.js`)

### UI

- **Copy button**: `CopyButton` component added to completed stream messages and static assistant messages. Visible on hover, shows "Copied!" feedback for 2s. (`frontend-react/src/components/CopyButton.jsx`)
- **Skeleton loading**: `MessageList` shows shimmer skeleton blocks when a session is loading and messages are empty. (`frontend-react/src/components/MessageList.jsx`, `frontend-react/src/styles.css`)
- **Session filter debounce**: `SessionSidebar` filter input uses local state for responsive typing with 200ms debounce to the store. (`frontend-react/src/features/sessions/SessionSidebar.jsx`)
- **Mobile breakpoint**: New `@media (max-width: 600px)` breakpoint with full-screen sidebar overlay, smaller header, wider messages. (`frontend-react/src/styles.css`)

### Code Cleanup

- **Legacy removal**: Removed `LegacyApp` component, `useChatStream` hook, `CHAT_V2_LAYOUT` feature flag, and `stream.js` re-export barrel. (`frontend-react/src/App.jsx`, deleted `frontend-react/src/hooks/useChatStream.js`, `frontend-react/src/shared/lib/features.js`, `frontend-react/src/stream.js`)
- **Test migration**: `stream.test.js` and `stream.fixtures.test.js` now import directly from `shared/lib/sse/parseEventStream` instead of the deleted barrel.

## 2026-03-03 (Backend Hardening: Security, Robustness, Code Quality)

### Summary

Comprehensive backend optimization pass addressing security boundaries, input validation, streaming robustness, observability, and code quality.

### Security

- **Payload size limit**: `read_json_body()` now enforces a 10 MB cap via `PayloadTooLargeError` → HTTP 413. Guards negative and non-numeric `Content-Length` headers. (`backend/http_utils.py`)
- **Path traversal fix**: `serve_static()` replaced fragile `str.startswith()` check with `Path.relative_to()`. (`backend/http_utils.py`)
- **Error sanitization**: `serve_static()` no longer exposes internal path details to clients; errors logged server-side. (`backend/http_utils.py`)

### Robustness

- **Request validation**: Message length capped at 100k chars (raises `ValidationError`); history items filtered to valid `{role: str, content: str}` dicts (max 100); images filtered to strings (max 10). (`backend/schemas.py`)
- **413 routing**: `handle_chat_once` and `handle_chat_stream` now catch `PayloadTooLargeError` → 413 before the generic 400 path. (`backend/chat_handlers.py`)
- **Agent timeout**: `stream_agentic()` drain loop enforces a 600-second soft deadline; emits `error` + `done(error)` on timeout. (`backend/event_mapper.py`)
- **Upstream error truncation**: `normalize_upstream_error()` caps `raw_body` at 5 KB to prevent memory bloat from oversized error payloads. (`backend/provider_event_normalizer.py`)

### Observability

- **SSE parse logging**: All 4 stream methods in `ProxyGatewayChatModel` now log `warning` when an SSE event fails JSON parsing (truncated to 200 chars). (`backend/proxy_chat_model.py`)
- **Search error logging**: `SearchProvider.search_with_events()` logs `warning` with stack trace on failure. (`backend/search_provider.py`)

### Performance & Code Quality

- **Registry index**: `model_registry.py` builds an `_INDEX` dict at module load for O(1) `get_by_id()` lookups. (`backend/model_registry.py`)
- **Simplified logic**: `_should_use_agentic_flow()` reduced from 3 branches to 2 (redundant `agent_mode is True` branch removed). (`backend/nvidia_client.py`)
- **Avoid duplicate work**: `_build_nvidia_chat_model()` now receives `pcfg` as parameter instead of re-calling `get_params()`. (`backend/model_profile.py`)
- **Named constants**: Extracted magic numbers in `message_builder.py` to `_MAX_MEDIA_ITEMS`, `_MAX_HISTORY_ITEMS`, `_MAX_URL_DISPLAY_CHARS`, `_CHARS_PER_TOKEN`, `_OVERHEAD_TOKENS_PER_MSG`.

### Tests Added

- `test_http_utils.py`: payload size limit, path traversal, error detail absence
- `test_chat_handlers.py`: 413 for oversized payloads
- `test_schemas.py`: message length, history filtering, image filtering
- `test_event_mapper.py` (new): agent timeout emits error + done sequence
- `test_proxy_chat_model.py`: malformed SSE event triggers warning log
- `test_search_provider.py`: search failure triggers warning log

### Files Modified

- `backend/http_utils.py`, `backend/chat_handlers.py`, `backend/schemas.py`
- `backend/proxy_chat_model.py`, `backend/event_mapper.py`, `backend/search_provider.py`
- `backend/model_registry.py`, `backend/nvidia_client.py`, `backend/model_profile.py`
- `backend/message_builder.py`, `backend/provider_event_normalizer.py`
- `tests/test_http_utils.py`, `tests/test_chat_handlers.py`, `tests/test_schemas.py`
- `tests/test_event_mapper.py` (new), `tests/test_proxy_chat_model.py`, `tests/test_search_provider.py`

---

## 2026-03-03 (Consolidate Google Models to gemini-3-pro-preview)

### Summary

Replaced `google/gemini-2.5-flash` and `google/gemini-3-flash-preview` with a single `google/gemini-3-pro-preview` model entry. All Google thinking/reasoning support (thinkingConfig, thought-part parsing) carries over unchanged.

### Files Modified

- `backend/model_registry.py`: two Google entries replaced with one `google/gemini-3-pro-preview`
- `api_examples.py`: updated model name and response comment
- `tests/test_model_registry.py`, `tests/test_model_profile.py`, `tests/test_proxy_chat_model.py`, `tests/test_nvidia_client.py`: all Google model references updated
- `CLAUDE.md`, `AGENTS.md`, `README.md`: model list updated

---

## 2026-03-03 (Add Gemini 2.5 Flash + Google Thinking Support)

### Summary

Added `google/gemini-2.5-flash` as a fully supported model (thinking, agent, SSE streaming) and implemented thinking/reasoning support for all Google models via the `thought: true` part flag in the Gemini generateContent API.

### Backend

- **Model registry**: New `google/gemini-2.5-flash` entry (provider: google, protocol: google_generate_content, context: 1M tokens, agent-capable with thinking)
- **Google thinking support**: `_invoke_google` and `_stream_google` in `proxy_chat_model.py` now detect `thought: true` on response parts and route them as `reasoning_content` (same pattern as Anthropic thinking_delta and OpenAI reasoning.delta)
- **thinkingConfig**: Google request body includes `generationConfig.thinkingConfig.thinkingBudget` when `thinking_mode` is enabled
- **Refactored**: Extracted `_build_google_body` shared helper for invoke/stream body+header construction (mirrors `_build_openai_body` pattern)

### Tests

- `test_known_models_present`: added `google/gemini-2.5-flash`
- `test_gemini_25_flash_capabilities`: thinking + agent enabled, media disabled
- `test_gemini_25_flash_metadata`: provider=google, upstream=gemini-2.5-flash, protocol=google_generate_content, context=1048576

### Files Modified

- `backend/model_registry.py`: new registry entry
- `backend/proxy_chat_model.py`: `_build_google_body`, `_invoke_google`, `_stream_google` updated
- `tests/test_model_registry.py`: 3 new/updated assertions
- `CLAUDE.md`, `AGENTS.md`: model list + protocol notes updated

---

## 2026-03-03 (Fix Multi-Message Loading State)

### Summary

Fixed issue where previously completed answers would show loading-like visual state (flicker, animation replays) when a new question was being streamed in the same conversation. Root cause: `syncSessionToCache` deep-cloned the entire session on every stream event, creating new object references for all messages and forcing re-renders of all `StreamMessage` components.

### Frontend

- **Incremental cache update**: During streaming, only the active stream message is replaced in the React Query cache; other messages retain their original references (`patchStreamMessageInCache` in `useSendMessage.js`)
- **React.memo on StreamMessage**: Default shallow comparison now naturally skips re-renders for unchanged messages (enabled by incremental updates preserving references)
- **Defensive `onDone` handler**: Finalizes message `status` to `"done"` even if the server closes the connection without sending a `done` SSE event
- **Sidebar invalidation reduction**: Session list cache is only invalidated on `done`/`error` events, not on every token
- **CSS `stream-done` class**: Completed stream messages get `animation: none` to prevent entry animation replays

### Tests

- 3 new unit tests in `MessageList.test.jsx` for multi-turn typing indicator isolation
- 1 new unit test for `stream-done` CSS class application
- 5 new tests in `patchStreamMessageInCache.test.js` for incremental cache update correctness and reference preservation
- 1 new E2E test: multi-turn conversation verifies completed answers have no typing dots and carry `stream-done` class

### Files Modified

- `frontend-react/src/features/chat/useSendMessage.js`: incremental cache updates + defensive onDone
- `frontend-react/src/components/StreamMessage.jsx`: React.memo + stream-done class
- `frontend-react/src/styles.css`: `.stream-done` animation override rules
- `frontend-react/src/__tests__/MessageList.test.jsx`: 4 new test cases
- `frontend-react/src/__tests__/patchStreamMessageInCache.test.js`: new test file (5 tests)
- `frontend-react/tests/e2e/chat-stream.spec.ts`: 1 new E2E test

---

## 2026-03-03 (OpenAI Codex 400 Fix + Test Coverage Expansion)

### Summary

Fixed OpenAI Codex streaming returning 400 from the proxy due to invalid request body fields. Expanded test coverage for `proxy_chat_model.py` with 19 new tests covering SSE parsing, provider dispatch, utility functions, and edge cases.

### Bug Fixes

- **P9 (400 error)**: Removed `temperature` and `top_p` from OpenAI Responses API request body - the `/responses` endpoint does not accept these as top-level fields, causing `status=400 type=request_error`
- **P10 (reasoning required)**: `reasoning` field is now always included in OpenAI requests - proxy requires it. Uses `effort: "high"` when `thinking_mode=True`, `effort: "low"` when `thinking_mode=False`

### Tests

- **Updated**: `test_openai_invoke_includes_temperature_top_p` -> renamed to `test_openai_body_omits_temperature_top_p` with flipped assertions
- **New test class `TestIterSseEvents`** (6 tests): direct unit tests for `_iter_sse_events` - basic parsing, multiline data, comment lines, no-blank-separator gateway quirk, empty stream, DONE marker
- **New test class `TestDispatchEdgeCases`** (4 tests): unsupported provider raises, Anthropic stream body includes system prompt, OpenAI thinking_mode=false produces `reasoning.effort=low`
- **New test class `TestUtilityFunctions`** (10 tests): `_messages_to_role_content` with ToolMessage, `_detail_from_exception` passthrough and normalization, `_json_post` HTTP errors with/without model_id, `bind_tools` returns copy, `_safe_json_loads` variants
- **New test class `TestParseEdgeCases`** (3 tests): `_parse_openai_completed` with empty/malformed output, stream fallback with no deltas and no text
- Total: 189 tests passing (was 155)

### Files Modified

- `backend/proxy_chat_model.py`: `_build_openai_body` - removed `temperature`/`top_p`, always include `reasoning`
- `tests/test_proxy_chat_model.py`: updated 1 existing test, added 19 new tests across 4 test classes

---

## 2026-03-03 (Multi-Provider Proxy Integration - Claude / Codex / Gemini)

### Summary

Added multi-provider backend support for Anthropic Claude Sonnet 4.6, OpenAI GPT-5.3 Codex, and Google Gemini 3 Flash via `ProxyGatewayChatModel`, a LangChain `BaseChatModel` adapter that routes through a configurable proxy gateway. All three providers now support real SSE streaming, agent tool-calling, and normalized error diagnostics.

### Backend

- **New files**:
  - `backend/proxy_chat_model.py`: LangChain `BaseChatModel` subclass adapting Anthropic Messages API, OpenAI Responses API, and Google generateContent API
  - `backend/provider_router.py`: registry-driven provider routing (`build_routed_chat_model`)
  - `backend/provider_event_normalizer.py`: unified upstream error parsing and diagnostics
- **Modified files**:
  - `backend/model_registry.py`: added 3 new model entries (`anthropic/claude-sonnet-4-6`, `openai/gpt-5.3-codex` as default, `google/gemini-3-flash-preview`) with provider/protocol/capabilities metadata
  - `backend/model_profile.py`: added `ProxyGatewayChatModel` construction path for non-NVIDIA providers; base URL normalization for proxy endpoints
  - `backend/config.py`: added `provider_credentials()` with multi-name env fallback chains (e.g. `ANTHROPIC_API_KEY` -> `CLAUDE_CLIENT_TOKEN_1` -> fallback)
  - `backend/nvidia_client.py`: replaced direct model construction with `provider_router.build_routed_chat_model()`
  - `backend/chat_handlers.py`: integrated `provider_event_normalizer` for error diagnostics in both stream and one-shot handlers

### Provider Streaming

- **Anthropic**: `_stream_anthropic` - SSE via `stream: true`, parses `content_block_delta` events (`text_delta` + `thinking_delta`)
- **OpenAI**: `_stream_openai` - SSE via `stream: true` (proxy requires it), parses `response.output_text.delta` + `response.reasoning_summary_text.delta`; fixed double-text emission with `had_text_deltas` guard
- **Google**: `_stream_google` - SSE via `streamGenerateContent?alt=sse`, parses chunked `candidates[].content.parts[].text`
- **OpenAI invoke**: `_invoke_openai` consumes SSE stream and aggregates `response.completed` (proxy rejects `stream: false`)

### Bug Fixes

- P0: OpenAI `_invoke_openai` now uses `stream: true` + SSE aggregation (proxy rejects `stream: false`)
- P1: `_stream_openai` no longer emits duplicate text from both delta events and `response.completed`
- P3: Google requests now include `generationConfig` with `temperature`, `topP`, `maxOutputTokens`
- P4: Google system prompts use `systemInstruction` field instead of injecting as user message
- P6: `_json_post` error path now uses `normalize_upstream_error` for consistent diagnostics
- P8: OpenAI requests now follow Responses API constraints: omit top-level `temperature`/`top_p` and always include `reasoning`

### Tests

- New test file: `tests/test_proxy_chat_model.py` - covers invoke + stream for all 3 providers
- New test file: `tests/test_provider_event_normalizer.py` - error payload parsing and normalization
- New test file: `tests/test_model_profile.py` - provider construction and env compat names
- New tests: `test_google_request_includes_generation_config`, `test_google_system_prompt_uses_system_instruction`, `test_openai_stream_no_double_text_when_deltas_present`, `test_openai_body_omits_temperature_top_p`, `test_openai_body_always_includes_reasoning`, `test_anthropic_stream_text_deltas`, `test_anthropic_stream_thinking_deltas`, `test_anthropic_stream_sends_stream_true`, `test_google_stream_text_chunks`, `test_google_stream_uses_stream_endpoint`
- Total: 155 tests passing

### Configuration

- Env variables for non-NVIDIA providers:
  - `ANTHROPIC_API_KEY` / `CLAUDE_CLIENT_TOKEN_1` / `CLAUDE_CLIENT_TOKEN`
  - `OPENAI_API_KEY` / `CODEX_TOKEN_1` / `CODEX_TOKEN`
  - `GOOGLE_API_KEY` / `GEMINI_API_KEY_1` / `GEMINI_API_KEY`
  - `ANTHROPIC_BASE_URL` / `CLAUDE_API_URL`
  - `OPENAI_BASE_URL` / `CODEX_API_URL`
  - `GOOGLE_BASE_URL` / `GOOGLE_GEMINI_BASE_URL`

## 2026-03-02 (Web Loader Parallelization and Timeout Controls)

### Summary

Improved web page loading performance for search context injection by introducing parallel fetching with bounded per-page timeout and total budget limits. This keeps default `include_page_content=True` behavior while reducing long-tail request latency.

### Backend

- Updated `backend/web_search.py`:
  - added parallel page-content loading via `ThreadPoolExecutor`
  - added total budget cutoff via `as_completed(..., timeout=...)`
  - preserved per-URL fallback chain: `WebBaseLoader` -> `requests + bs4`
  - added optional parameters on `web_search(...)`:
    - `page_timeout_s`
    - `total_budget_s`
    - `max_pages`
    - `concurrency`
  - added optional `timeout_s` to `load_webpage_content(...)`
- Updated `backend/nvidia_client.py` `_run_web_search(...)` to accept and forward the new runtime controls.

### Configuration

- Added environment options:
  - `WEB_LOADER_TIMEOUT_SECONDS` (default `2.0`)
  - `WEB_SEARCH_TOTAL_BUDGET_SECONDS` (default `4.0`)
  - `WEB_LOADER_MAX_PAGES` (default `3`)
  - `WEB_LOADER_CONCURRENCY` (default `3`)
- Documented these variables in `.env.example` and `README.md`.

## 2026-02-28 (Frontend V2 Session Refactor + Robust Tests)

### Summary

Frontend chat was refactored into a session-centric architecture with clear data/state boundaries, pluggable persistence abstraction, and stronger stream isolation. Test coverage was expanded across unit/component/integration layers with new SSE fixture regressions.

### Frontend Architecture

- Added provider and domain layers:
  - `frontend-react/src/app/AppProviders.jsx`
  - `frontend-react/src/entities/session/*`
  - `frontend-react/src/features/sessions/*`
  - `frontend-react/src/features/chat/*`
  - `frontend-react/src/shared/store/*`
  - `frontend-react/src/shared/api/*`
  - `frontend-react/src/shared/lib/*`
- Introduced session repository abstraction with first implementation:
  - `MemorySessionRepository` (pluggable for future IndexedDB/backend sync)
- Added session sidebar/list UI with title/time/preview rendering and per-session switching.
- Added stream pipeline split:
  - `useSendMessage`
  - `useStreamController`
  - `mapStreamEventToPatch`
- Added request isolation invariant in frontend runtime:
  - stream updates are validated by `sessionId + requestId`.

### SSE + Stream Handling

- Moved parser implementation to `frontend-react/src/shared/lib/sse/parseEventStream.js`.
- Kept compatibility export via `frontend-react/src/stream.js`.
- Hardened parser line-ending handling (`LF` and `CRLF`) to avoid fixture/runtime mismatch.

### Tests

- Added unit tests:
  - `src/__tests__/mapStreamEventToPatch.test.js`
  - `src/__tests__/memorySessionRepository.test.js`
  - `src/__tests__/chatUiStore.test.js`
  - `src/__tests__/sessionSummary.test.js`
- Added component/integration tests:
  - `src/__tests__/SessionList.test.jsx`
  - updated `src/__tests__/App.behavior.test.jsx` with session creation, error invariant, and cross-session stream isolation.
- Added fixture-driven SSE parser regression tests:
  - `src/__tests__/stream.fixtures.test.js`
- Added SSE fixture files:
  - `stream-error-then-done.txt`
  - `stream-search-usage-reasoning.txt`
  - `stream-malformed-lines.txt`
  - `stream-cross-session-interleaving.txt`

### Verification

- `cd frontend-react && pnpm test` passed (`24` tests).
- `cd frontend-react && pnpm run build` passed.

## 2026-02-28 (Agentic Refactoring)

### Summary

Backend agent system rewritten from LangChain `AgentExecutor` (3-step, 1 tool) to LangGraph `StateGraph` with Plan -> Act -> Observe -> Reflect loop, multiple tools, configurable iteration limits, and token-by-token streaming of final answers.

### Agent Architecture

- Replaced `AgentExecutor` with LangGraph `StateGraph` in new `backend/agent_graph.py`:
  - **plan_node**: optional planning phase before tool use
  - **agent_node**: LLM decision (call tool or answer)
  - **execute_tools_node**: runs tools with `tool_call`/`tool_result` event emission
  - **reflect_node**: periodic self-evaluation (every 3 steps, configurable)
  - **stream_answer_node**: token-by-token streaming of final answer via `client.stream()`
- Configurable max steps per model (default 8, was hardcoded 3)
- Agent emits all events (including tokens) via `event_emitter`; no longer returns a string

### New Tools

- `read_url`: fetches and reads web page content (reuses `web_search.load_webpage_content`)
- `python_exec`: sandboxed Python code execution via subprocess (opt-in via `ENABLE_CODE_INTERPRETER=1`)
- Tool selection per-model via `agent_config.tools` in model registry
- `build_agent_tools()` now accepts `enabled_tools` filter parameter

### New SSE Events (backward-compatible)

- `agent_plan`, `agent_step_start`, `agent_step_end`, `tool_call`, `tool_result`, `agent_reflect`

### Files Changed

- **New**: `backend/agent_graph.py`, `tests/test_agent_graph.py`
- **Rewritten**: `backend/agent_orchestrator.py`, `backend/tools_registry.py`
- **Modified**: `backend/event_mapper.py`, `backend/nvidia_client.py`, `backend/model_registry.py`, `requirements.txt`

---

## 2026-02-28

### Summary

This release consolidates the backend into a modular architecture, introduces a model capabilities API consumed by frontend, hardens SSE protocol behavior, refactors frontend into hooks/components/utils, and significantly expands test coverage.

### Frontend Auto-Scroll Hardening (follow-up)

- Fixed chat auto-scroll stickiness regression in `frontend-react/src/hooks/useChatStream.js`:
  - switched from post-update near-bottom inference to scroll-intent tracking
  - added `handleMessagesScroll` + `stickToBottomRef` with a `150px` threshold
- Wired scroll event propagation through:
  - `frontend-react/src/components/MessageList.jsx`
  - `frontend-react/src/App.jsx`
- Added robust frontend behavior tests in `frontend-react/src/__tests__/App.behavior.test.jsx` for:
  - stick-to-bottom while streaming
  - no forced scroll while user reads history
  - resume follow when user returns near bottom
  - large height jump handling
  - threshold edge cases (`149/150/151`)
  - unmount safety during deferred animation callbacks
- Added/updated e2e coverage in `frontend-react/tests/e2e/chat-stream.spec.ts`:
  - follow behavior at bottom
  - scroll-up disables follow until user returns
- Improved e2e SSE fixture reliability in `frontend-react/tests/helpers/mockSse.ts`:
  - normalize CRLF to LF for parser compatibility
  - route matcher widened to `**/api/chat/stream*`
  - send action uses `#sendBtn` click for stable submission
- Added long-stream fixture: `frontend-react/tests/fixtures/sse/stream-multi-token.txt`

### Backend

- Refactored `backend/nvidia_client.py` into a facade and extracted heavy logic into:
  - `backend/model_registry.py`
  - `backend/model_profile.py`
  - `backend/message_builder.py`
  - `backend/agent_orchestrator.py`
  - `backend/event_mapper.py`
  - `backend/search_provider.py`
  - `backend/schemas.py`
- Switched agent implementation to LangChain `create_tool_calling_agent` via `backend/agent_orchestrator.py`.
- Added centralized model registry as single source of truth:
  - model list
  - default model
  - capability flags (`thinking`, `media`, `agent`)
  - context window
  - model-specific request parameter strategy
- Updated `backend/config.py` model resolution to use registry defaults instead of hardcoded tuples.
- Added request schema parsing with `ChatRequest` dataclass (`backend/schemas.py`) to standardize payload handling.

### SSE and API Behavior

- Added event enrichment in `backend/http_utils.py`:
  - all SSE events include `v: 1`
  - include `request_id` when available
- Updated stream handlers to propagate request id consistently:
  - `backend/chat_handlers.py` now emits SSE events with request correlation
- Strengthened error flow semantics:
  - stream timeout/gateway/internal errors emit `error` and then `done` with `finish_reason: "error"`
- Added capabilities endpoint:
  - local server route: `GET /api/capabilities` in `backend/server.py`
  - vercel wrapper: `api/capabilities.py`
  - vercel rewrite: `vercel.json`

### Search and Agent Event Flow

- Unified web-search event emission through `SearchProvider`:
  - consistent `search_start` / `search_done` / `search_error`
  - shared by agent and non-agent paths
- Added explicit stream generators in `backend/event_mapper.py`:
  - `stream_agentic`
  - `stream_direct`
- Added fallback token behavior for empty outputs:
  - direct stream fallback when no visible token produced
  - agentic fallback when agent returns empty/whitespace final answer

### Frontend

- Refactored monolithic `frontend-react/src/App.jsx` into:
  - hooks:
    - `useCapabilities`
    - `useChatStream`
    - `useAttachments`
  - components:
    - `Composer`
    - `MessageList`
    - `StreamMessage`
    - `ModelSelect`
    - `AttachStrip`
    - `RichBlock`
    - `CollapsibleSection`
  - utils:
    - `models.js`
    - `media.js`
    - `markdown.js`
- Frontend now fetches runtime model metadata from `GET /api/capabilities` with local fallback.
- Updated UI strings to English in key interactive areas.
- Maintained streaming panels: Search, Context Usage, Reasoning, Answer.

### Frontend Reliability Fixes (same release)

- Fixed SSE error propagation in `frontend-react/src/stream.js`:
  - parsing errors are caught
  - application-level event handler errors are no longer swallowed
- Fixed stream error handling in `frontend-react/src/hooks/useChatStream.js`:
  - error events no longer degrade into `(empty response)`
  - failed streams do not append empty assistant responses into history
- Fixed capabilities race condition in `frontend-react/src/hooks/useCapabilities.js`:
  - preserves user-selected model when capabilities fetch resolves later
  - still falls back to valid model when selected model is absent in incoming capabilities

### Tests

- Added backend tests:
  - `tests/test_model_registry.py`
  - `tests/test_schemas.py`
  - `tests/test_search_provider.py`
  - `tests/test_http_utils.py`
  - `tests/test_empty_response_diagnosis.py`
- Expanded backend assertions in:
  - `tests/test_chat_handlers.py`
  - `tests/test_nvidia_client.py`
  - `tests/test_tools_registry.py`
- Expanded frontend behavior tests in:
  - `frontend-react/src/__tests__/App.behavior.test.jsx`
  - coverage includes stream error display, error+done behavior, capabilities defaulting, and model selection race scenarios

### Tooling and Build

- Updated frontend Vitest config (`frontend-react/vitest.config.js`) to exclude `tests/**` and `node_modules/**`.
- Updated frontend lockfile (`frontend-react/pnpm-lock.yaml`).
- Rebuilt frontend distribution assets in `frontend/dist`.

### Documentation

- Updated:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `README.md` (migrated from `default.md`)
- Added this canonical release history file: `CHANGELOG.md`.
- Documentation cleanup:
  - removed `GEMINI.md`
  - condensed `AGENTS.md` and `CLAUDE.md` without changing behavior contracts

## 2026-02-10

### Summary

Initial React/Vite migration and CI/CD integration milestone.

### Changes

- Frontend migrated to React + Vite (`frontend-react`).
- Backend static serving switched to `frontend/dist` output.
- Introduced richer chat UI sections and animation treatment.
- Added CI workflows and Vercel deployment flow.

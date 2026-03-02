# CHANGELOG

All notable changes to this repository are documented in this file.

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

Backend agent system rewritten from LangChain `AgentExecutor` (3-step, 1 tool) to LangGraph `StateGraph` with Plan → Act → Observe → Reflect loop, multiple tools, configurable iteration limits, and token-by-token streaming of final answers.

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

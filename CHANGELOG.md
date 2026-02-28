# CHANGELOG

All notable changes to this repository are documented in this file.

## 2026-02-28

### Summary

This release consolidates the backend into a modular architecture, introduces a model capabilities API consumed by frontend, hardens SSE protocol behavior, refactors frontend into hooks/components/utils, and significantly expands test coverage.

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

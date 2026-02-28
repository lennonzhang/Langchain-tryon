# CLAUDE.md

Quick operating notes for Claude Code in this repo.

## Overview

Full-stack LangChain chat app:

- Backend: Python `http.server` style API + static serving
- Frontend: React + Vite output served from `frontend/dist`
- Features: streaming SSE, web search, reasoning stream, optional multimodal input, tool-calling agent flow

Default endpoint: `POST /api/chat/stream`.

## Commands

```bash
# backend
python server.py
python -m unittest discover -s tests -v

# frontend (from frontend-react/)
pnpm install
pnpm run dev
pnpm run build
pnpm test
pnpm test:e2e
```

## Runtime Baseline

- Python `3.12+`
- Node `22.22.0`
- pnpm `10+`

## Architecture Map

- `backend/nvidia_client.py`: public facade (`chat_once`, `stream_chat`)
- `backend/model_registry.py`: model capability source of truth
- `backend/model_profile.py`: model params/build logic
- `backend/message_builder.py`: message/media assembly + token estimate
- `backend/agent_orchestrator.py`: `create_tool_calling_agent` flow
- `backend/event_mapper.py`: direct/agent streaming event generation
- `backend/search_provider.py`: unified search event emission
- `backend/tools_registry.py`: LangChain tools
- `backend/schemas.py`: request schema parsing
- `backend/chat_handlers.py`: route handlers
- `backend/http_utils.py`: JSON/SSE helpers
- `frontend-react/src/App.jsx`: frontend composition root
- `frontend-react/src/hooks/*`, `components/*`, `utils/*`: frontend state and UI modules
- `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`: Vercel wrappers

## Key Paths

- `backend/model_registry.py`: model capabilities/defaults source of truth
- `backend/model_profile.py`: model construction and invoke/stream kwargs
- `backend/message_builder.py`: history/media normalization, message construction
- `backend/agent_orchestrator.py`: tool-calling agent execution
- `backend/event_mapper.py`: direct/agent streaming event generation
- `backend/search_provider.py`: shared search event emitter
- `backend/tools_registry.py`: LangChain tool definitions
- `backend/schemas.py`: request payload parsing (`ChatRequest`)
- `backend/chat_handlers.py`: `/api/chat` and `/api/chat/stream` handlers
- `backend/http_utils.py`: `send_json`, `send_sse_event`, static file serving helpers
- `backend/nvidia_client.py`: facade entrypoint for chat logic
- `backend/server.py`: local HTTP entrypoint and routing
- `frontend-react/src/App.jsx`: app composition
- `frontend-react/src/hooks/useCapabilities.js`: capability bootstrap and model selection
- `frontend-react/src/hooks/useChatStream.js`: streaming state machine
- `frontend-react/src/hooks/useAttachments.js`: media attachment workflow
- `frontend-react/src/components/MessageList.jsx`: message list container + scroll event boundary
- `frontend-react/src/stream.js`: SSE parser
- `frontend-react/tests/e2e/chat-stream.spec.ts`: end-to-end chat stream behavior coverage
- `frontend-react/tests/helpers/mockSse.ts`: e2e SSE route mocking + fixture normalization
- `frontend-react/tests/fixtures/sse/*`: SSE fixture files (including multi-token stream cases)
- `api/capabilities.py`: serverless capabilities endpoint
- `api/chat.py`, `api/chat/stream.py`: serverless chat wrappers

## API + SSE Contract

Request fields:

- `message` (required), `history`, `model`, `web_search`, `agent_mode`, `thinking_mode`, `images`, `request_id`

SSE events:

- `search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`, `error`, `done`
- Enrichment: `v: 1`, plus `request_id` when available
- Error invariant: `error` then `done` (`finish_reason: "error"`)

## Model Rules

- Supported: `moonshotai/kimi-k2.5` (default), `qwen/qwen3.5-397b-a17b`, `z-ai/glm5`
- Auto `agent_mode` when omitted:
  - on: qwen, glm
  - off: kimi
- If model supports reasoning and `thinking_mode=true`, stream reasoning events

## Frontend Notes

- Chat auto-scroll rule: only follow stream when message list is near bottom (`<= 150px`); preserve user position when they scroll up.
- E2E SSE fixture handling should use LF-normalized content to match `frontend-react/src/stream.js` block splitting.

## Documentation Rule

When behavior changes:

- update `AGENTS.md`, `CLAUDE.md`, `README.md` as needed
- append detailed entry to `CHANGELOG.md`

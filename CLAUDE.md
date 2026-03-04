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
- `backend/model_registry.py`: model capability source of truth (provider, protocol, params)
- `backend/model_profile.py`: model params/build logic, env resolution
- `backend/proxy_chat_model.py`: LangChain `BaseChatModel` adapter for non-NVIDIA providers (Anthropic, OpenAI, Google)
- `backend/provider_router.py`: provider-aware model instantiation
- `backend/provider_event_normalizer.py`: unified upstream error diagnostics
- `backend/message_builder.py`: message/media assembly + token estimate
- `backend/agent_graph.py`: LangGraph StateGraph (Plan -> Act -> Observe -> Reflect)
- `backend/agent_orchestrator.py`: agent entry point, builds graph and invokes
- `backend/event_mapper.py`: direct/agent streaming event generation
- `backend/search_provider.py`: unified search event emission
- `backend/tools_registry.py`: LangChain tools (web_search, read_url, python_exec)
- `backend/schemas.py`: request schema parsing
- `backend/chat_handlers.py`: route handlers
- `backend/http_utils.py`: JSON/SSE helpers
- `backend/config.py`: env loading, API key/base URL resolution per provider
- `frontend-react/src/App.jsx`: frontend composition root
- `frontend-react/src/app/AppProviders.jsx`: frontend provider root (query + repository)
- `frontend-react/src/features/sessions/*`: session list/data hooks
- `frontend-react/src/features/chat/*`: send pipeline, stream controller, event mapping
- `frontend-react/src/entities/session/*`: session summaries + in-memory repository
- `frontend-react/src/shared/store/chatUiStore.js`: global UI/runtime state
- `frontend-react/src/shared/api/chatApiClient.js`: capabilities + stream transport (AbortController support, `onDone` awaited)
- `frontend-react/src/shared/lib/sse/parseEventStream.js`: SSE parsing (LF/CRLF tolerant)
- `frontend-react/src/components/ErrorBoundary.jsx`: React error boundary (app + per-message)
- `frontend-react/src/components/CopyButton.jsx`: clipboard copy with visual feedback
- `frontend-react/src/hooks/*`, `components/*`, `utils/*`: frontend state and UI modules
- `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`: Vercel wrappers

## Key Paths

- `backend/model_registry.py`: model capabilities/defaults source of truth
- `backend/model_profile.py`: model construction and invoke/stream kwargs
- `backend/proxy_chat_model.py`: multi-provider LangChain adapter (invoke + SSE stream)
- `backend/provider_router.py`: registry-driven provider routing
- `backend/provider_event_normalizer.py`: upstream error normalization
- `backend/config.py`: env loading, `provider_credentials()`, `resolve_model()`
- `backend/message_builder.py`: history/media normalization, message construction
- `backend/agent_graph.py`: LangGraph agent graph definition (nodes, edges, state)
- `backend/agent_orchestrator.py`: agent entry point and graph invocation
- `backend/event_mapper.py`: direct/agent streaming event generation
- `backend/search_provider.py`: shared search event emitter
- `backend/tools_registry.py`: LangChain tool definitions
- `backend/schemas.py`: request payload parsing (`ChatRequest`)
- `backend/chat_handlers.py`: `/api/chat` and `/api/chat/stream` handlers
- `backend/http_utils.py`: `send_json`, `send_sse_event`, static file serving helpers
- `backend/nvidia_client.py`: facade entrypoint for chat logic
- `backend/server.py`: local HTTP entrypoint and routing
- `frontend-react/src/App.jsx`: app composition
- `frontend-react/src/app/AppProviders.jsx`: app-level providers
- `frontend-react/src/features/sessions/useSessions.js`: session query/mutation hooks
- `frontend-react/src/features/chat/useSendMessage.js`: session-aware stream send pipeline (`finalizeStreamOnce` terminal single-exit)
- `frontend-react/src/features/chat/mapStreamEventToPatch.js`: stream event reducer
- `frontend-react/src/shared/store/chatUiStore.js`: UI/runtime store
- `frontend-react/src/hooks/useCapabilities.js`: capability bootstrap and model selection
- `frontend-react/src/hooks/useAttachments.js`: media attachment workflow
- `frontend-react/src/components/MessageList.jsx`: message list container + scroll event boundary (memoized items)
- `frontend-react/src/components/RichBlock.jsx`: markdown rendering with MathJax debounce
- `frontend-react/src/components/ErrorBoundary.jsx`: React error boundary (app-level + per-message)
- `frontend-react/src/components/CopyButton.jsx`: clipboard copy with feedback
- `frontend-react/tests/e2e/chat-stream.spec.ts`: end-to-end chat stream behavior coverage
- `frontend-react/tests/helpers/mockSse.ts`: e2e SSE route mocking + fixture normalization
- `frontend-react/tests/fixtures/sse/*`: SSE fixture files (including multi-token stream cases)
- `api/capabilities.py`: serverless capabilities endpoint
- `api/chat.py`, `api/chat/stream.py`: serverless chat wrappers

## API + SSE Contract

Request fields:

- `message` (required, max 100k chars), `history` (max 100, validated dicts), `model`, `web_search`, `agent_mode`, `thinking_mode`, `images` (max 10, strings only), `request_id`

Request limits:

- JSON body max size: 10 MB (413 Payload Too Large if exceeded)
- `message` max length: 100,000 characters (400 ValidationError)
- `history` max items: 100 (silently trimmed); items must be `{role: str, content: str}`
- `images` max items: 10 (silently trimmed); items must be strings

SSE events:

- Core: `search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`, `error`, `done`
- Agent: `agent_plan`, `agent_step_start`, `agent_step_end`, `tool_call`, `tool_result`, `agent_reflect`
- Enrichment: `v: 1`, plus `request_id` when available
- Error invariant: `error` then `done` (`finish_reason: "error"`)
- Agent timeout: 600s soft deadline; emits `error` + `done(error)` if exceeded

## Model Rules

- Supported models (source of truth: `backend/model_registry.py`):
  - NVIDIA: `moonshotai/kimi-k2.5`, `qwen/qwen3.5-397b-a17b`, `z-ai/glm5`
  - Anthropic: `anthropic/claude-sonnet-4-6` (via sssaicode proxy)
  - OpenAI: `openai/gpt-5.3-codex` (default, via sssaicode proxy)
  - Google: `google/gemini-3-pro-preview` (via sssaicode proxy)
- Default model: `openai/gpt-5.3-codex`
- Auto `agent_mode` when omitted:
  - on: qwen, glm, claude, codex, gemini
  - off: kimi
- If model supports reasoning and `thinking_mode=true`, stream reasoning events

## Multi-Provider Architecture

- All non-NVIDIA models route through `ProxyGatewayChatModel` (LangChain `BaseChatModel`)
- Provider protocols:
  - `anthropic_messages`: POST `/messages` (Anthropic Messages API, SSE stream)
  - `openai_responses`: POST `/responses` (OpenAI Responses API, SSE stream, `stream: true` required, `reasoning` required)
  - `google_generate_content`: POST `/models/{model}:generateContent` (invoke) or `:streamGenerateContent?alt=sse` (stream); `thinkingConfig` in `generationConfig` controls thinking budget; response parts with `thought: true` carry reasoning tokens
- OpenAI Responses API constraints:
  - `temperature` / `top_p` must NOT be sent as top-level fields (causes 400)
  - `reasoning` must always be present (`effort: "high"` when thinking, `effort: "low"` otherwise)
- Proxy base URLs default to `claude2.sssaicode.com` (configurable via env)
- API key resolution: provider-specific env -> compat names (e.g. `CLAUDE_CLIENT_TOKEN_1`) -> fallback
- Error normalization: `provider_event_normalizer.py` produces `provider=X | protocol=Y | status=Z | message=...`

## Frontend Notes

- Chat auto-scroll rule: only follow stream when message list is near bottom (`<= 150px`); preserve user position when they scroll up.
- E2E SSE fixture handling should use LF-normalized content to match `frontend-react/src/shared/lib/sse/parseEventStream.js` block splitting.
- Frontend stream policy is global single in-flight request; new sends do not auto-preempt existing streams, and user must stop the running session explicitly.
- Frontend terminal callbacks are awaited (`onDone`, `onTransportError`, `onAborted`) to prevent pending-state cleanup races.

## Documentation Rule

When behavior changes:

- update `AGENTS.md`, `CLAUDE.md` 
- append detailed entry to `CHANGELOG.md`
- update `README.md` if needed

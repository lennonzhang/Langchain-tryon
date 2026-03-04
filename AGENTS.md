# AGENTS.md

Repository-level guide for coding agents.

## Scope

- Applies to the whole repo unless a deeper folder overrides it.
- Keep changes minimal, testable, and aligned with current architecture.

## Runtime

- Python `3.12+`
- Node `22.22.0`
- pnpm `10+`
- Local app: `http://127.0.0.1:8000`

## Product Defaults

- Primary chat path: `POST /api/chat/stream`
- One-shot path: `POST /api/chat`
- Capabilities path: `GET /api/capabilities`
- `thinking_mode` default: `true`
- `agent_mode` default when omitted:
  - enabled: qwen, glm, claude, codex, gemini (all agent-capable models)
  - disabled: kimi

## SSE Contract

- Core events: `search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`, `error`, `done`
- Agent events: `agent_plan`, `agent_step_start`, `agent_step_end`, `tool_call`, `tool_result`, `agent_reflect`
- Every event includes `v: 1`
- Include `request_id` when available
- Error invariant: `error` must be followed by `done` with `finish_reason: "error"`
- Agent timeout: 600s soft deadline; exceeding emits `error` + `done(error)`
- Request body limit: 10 MB (413 if exceeded); message max 100k chars; history max 100 items; images max 10 items

## Model Policy

- Supported (source of truth: `backend/model_registry.py`):
  - NVIDIA: `moonshotai/kimi-k2.5`, `qwen/qwen3.5-397b-a17b`, `z-ai/glm5`
  - Anthropic: `anthropic/claude-sonnet-4-6`
  - OpenAI: `openai/gpt-5.3-codex` (default)
  - Google: `google/gemini-3-pro-preview`
- Non-NVIDIA models use `ProxyGatewayChatModel` with real SSE streaming
- Provider protocols: `anthropic_messages`, `openai_responses`, `google_generate_content`
- OpenAI Responses API: do not send `temperature`/`top_p` as top-level fields; always include `reasoning` (`effort: "high"` or `"low"`)
- If model supports reasoning and `thinking_mode=true`, stream `reasoning` events

## API Payload

- `message` (required), `history`, `model`, `web_search`, `agent_mode`, `thinking_mode`, `images`, `request_id`

## Architecture Rules

- Keep `backend/nvidia_client.py` as facade.
- Put detailed logic in extracted modules (`model_profile`, `message_builder`, `agent_graph`, `agent_orchestrator`, `event_mapper`, `search_provider`, `schemas`, `tools_registry`, `proxy_chat_model`, `provider_router`, `provider_event_normalizer`).
- Non-NVIDIA providers go through `ProxyGatewayChatModel`; do not add provider-specific logic to `nvidia_client.py`.
- Provider routing is registry-driven (`model_registry.py` -> `provider_router.py` -> `model_profile.py`).
- All providers must implement real SSE streaming (no fake-stream via full response).
- Use `SearchProvider` for both agent and non-agent search event emission.
- Do not rename SSE events silently.
- Update tests + docs together.
- Frontend chat auto-scroll policy: follow only when user is near bottom (threshold `150px`); do not force scroll after user scrolls up.
- For Playwright SSE fixtures, normalize line endings to LF before parsing.
- Frontend session/stream updates must be isolated by `sessionId + requestId`; do not allow cross-session stream writes.
- Frontend persistence remains repository-driven; avoid coupling UI directly to storage implementation.
- `ErrorBoundary` wraps `<AppContent>` at top level and each `<RichBlock>` in `StreamMessage`.
- Stream requests use `AbortController`; app policy allows only one in-flight stream globally and requires explicit user stop (no auto-preemption on new send).
- `useSendMessage` has a synchronous `sendingRef` mutex to prevent double-send races.
- Stream retry: max 1 retry on network/5xx errors, only if no tokens have been received yet.
- Stream terminal handling is single-exit + idempotent in `useSendMessage` (`finalizeStreamOnce`): first terminal signal wins among `done` / transport error / abort.
- `useStreamController` awaits terminal callbacks (`onTransportError`, `onAborted`), and `chatApiClient.streamChat` awaits `onDone` to avoid pending-cleanup races.
- `RichBlock` debounces MathJax typesetting by 500ms to avoid expensive re-typeset during streaming.
- `MessageList` items (`UserMessage`, `AssistantMessage`) are `memo()`-wrapped to prevent re-renders during streaming.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend-react
pnpm test
pnpm test:e2e
pnpm run build
```

## Key Paths

- Model registry: `backend/model_registry.py`
- Model profile/runtime params: `backend/model_profile.py`
- Multi-provider LangChain adapter: `backend/proxy_chat_model.py`
- Provider routing: `backend/provider_router.py`
- Upstream error normalization: `backend/provider_event_normalizer.py`
- Env/credentials: `backend/config.py`
- Message assembly/token estimate: `backend/message_builder.py`
- Agent graph (LangGraph): `backend/agent_graph.py`
- Agent orchestration: `backend/agent_orchestrator.py`
- Stream event mapping: `backend/event_mapper.py`
- Search abstraction: `backend/search_provider.py`
- Tool definitions: `backend/tools_registry.py`
- Request schema: `backend/schemas.py`
- Chat handlers: `backend/chat_handlers.py`
- HTTP/SSE utils: `backend/http_utils.py`
- Public facade API: `backend/nvidia_client.py`
- Server entry: `backend/server.py`
- Frontend root: `frontend-react/src/App.jsx`
- Frontend providers: `frontend-react/src/app/AppProviders.jsx`
- Frontend session feature: `frontend-react/src/features/sessions/*`
- Frontend chat feature: `frontend-react/src/features/chat/*`
- Frontend entities: `frontend-react/src/entities/*`
- Frontend shared store/api/lib: `frontend-react/src/shared/*`
- Frontend hooks: `frontend-react/src/hooks/*`
- Frontend components: `frontend-react/src/components/*`
- Frontend utils: `frontend-react/src/utils/*`
- Message list component: `frontend-react/src/components/MessageList.jsx`
- Error boundary: `frontend-react/src/components/ErrorBoundary.jsx`
- Copy button: `frontend-react/src/components/CopyButton.jsx`
- Stream parser: `frontend-react/src/shared/lib/sse/parseEventStream.js`
- Backend tests: `tests/test_*.py`
- Frontend tests: `frontend-react/src/__tests__/*`, `frontend-react/tests/*`
- Frontend e2e spec: `frontend-react/tests/e2e/chat-stream.spec.ts`
- Frontend e2e helper: `frontend-react/tests/helpers/mockSse.ts`
- Frontend SSE fixtures: `frontend-react/tests/fixtures/sse/*`
- Vercel wrappers: `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`
- Release notes: `CHANGELOG.md`

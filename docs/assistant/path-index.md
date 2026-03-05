# Path Index

**Purpose:** Deep path index for implementation and debugging entry points.  
**When to read:** When you already know the rule and need exact code locations.

## Backend

- Model capability source of truth (provider, protocol, params): `backend/model_registry.py`
- Model params/build logic, env resolution: `backend/model_profile.py`
- LangChain `BaseChatModel` adapter for non-NVIDIA providers (Anthropic, OpenAI, Google): `backend/proxy_chat_model.py`
- Provider-aware model instantiation (registry-driven): `backend/provider_router.py`
- Unified upstream error diagnostics: `backend/provider_event_normalizer.py`
- Env loading, API key/base URL resolution per provider: `backend/config.py`
- Message/media assembly + token estimate: `backend/message_builder.py`
- LangGraph StateGraph (Plan → Act → Observe → Reflect): `backend/agent_graph.py`
- Agent entry point, builds graph and invokes: `backend/agent_orchestrator.py`
- Direct/agent streaming event generation: `backend/event_mapper.py`
- Unified search event emission: `backend/search_provider.py`
- LangChain tools (web_search, read_url, python_exec): `backend/tools_registry.py`
- Request schema parsing (`ChatRequest`): `backend/schemas.py`
- `/api/chat` and `/api/chat/stream` route handlers: `backend/chat_handlers.py`
- `send_json`, `send_sse_event`, static file serving helpers: `backend/http_utils.py`
- Public facade (`chat_once`, `stream_chat`): `backend/nvidia_client.py`
- Local HTTP entrypoint and routing: `backend/server.py`

## Frontend

- Frontend composition root: `frontend-react/src/App.jsx`
- Frontend provider root (query + repository): `frontend-react/src/app/AppProviders.jsx`
- Session list/data hooks: `frontend-react/src/features/sessions/*`
- Send pipeline, stream controller, event mapping: `frontend-react/src/features/chat/*`
- Session query/mutation hooks: `frontend-react/src/features/sessions/useSessions.js`
- Session-aware stream send pipeline (`finalizeStreamOnce` terminal single-exit): `frontend-react/src/features/chat/useSendMessage.js`
- Stream event reducer: `frontend-react/src/features/chat/mapStreamEventToPatch.js`
- Session summaries + in-memory repository: `frontend-react/src/entities/*`
- Shared store/api/lib: `frontend-react/src/shared/*`
- Global UI/runtime state: `frontend-react/src/shared/store/chatUiStore.js`
- Capabilities + stream transport (AbortController support, `onDone` awaited): `frontend-react/src/shared/api/chatApiClient.js`
- SSE parsing (LF/CRLF tolerant): `frontend-react/src/shared/lib/sse/parseEventStream.js`
- Hooks: `frontend-react/src/hooks/*`
- Capability bootstrap and model selection: `frontend-react/src/hooks/useCapabilities.js`
- Media attachment workflow: `frontend-react/src/hooks/useAttachments.js`
- Components: `frontend-react/src/components/*`
- Message list container + scroll event boundary (memoized items): `frontend-react/src/components/MessageList.jsx`
- Markdown rendering with MathJax debounce: `frontend-react/src/components/RichBlock.jsx`
- React error boundary (app-level + per-message): `frontend-react/src/components/ErrorBoundary.jsx`
- Clipboard copy with visual feedback: `frontend-react/src/components/CopyButton.jsx`
- Utilities: `frontend-react/src/utils/*`

## Tests and Fixtures

- Backend tests: `tests/test_*.py`
- Frontend unit/integration tests: `frontend-react/src/__tests__/*`
- Frontend e2e tests: `frontend-react/tests/*`
- Chat stream e2e spec: `frontend-react/tests/e2e/chat-stream.spec.ts`
- SSE mock helper: `frontend-react/tests/helpers/mockSse.ts`
- SSE fixtures: `frontend-react/tests/fixtures/sse/*`

## Deployment and Docs

- Vercel wrappers: `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`
- Release notes: `CHANGELOG.md`
- Runtime/readme: `README.md`

## Related

- Architecture rules: [`./architecture-rules.md`](./architecture-rules.md)
- Validation + release checklist: [`./validation-and-release-checklist.md`](./validation-and-release-checklist.md)

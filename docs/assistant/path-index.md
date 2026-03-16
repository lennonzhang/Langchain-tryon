# Path Index

**Purpose:** Deep path index for implementation and debugging entry points.  
**When to read:** When you already know the rule and need exact code locations.

## Backend

- Model capability compatibility facade (provider, protocol, params): `backend/model_registry.py`
- Canonical model templates: `backend/domain/model_templates.py`
- Active env-driven model catalog: `backend/domain/model_catalog.py`
- Model params/build logic compatibility facade: `backend/model_profile.py`
- LangChain `BaseChatModel` adapter for non-NVIDIA providers (Anthropic, OpenAI, Google): `backend/proxy_chat_model.py`
- Provider protocol clients: `backend/infrastructure/protocols/*`
- Shared HTTP/SSE transport: `backend/infrastructure/transport/*`
- Provider-aware model instantiation (registry-driven): `backend/provider_router.py`
- Unified upstream error diagnostics: `backend/provider_event_normalizer.py`
- Env loading, API key/base URL resolution per provider: `backend/config.py`
- Env loader + provider settings + timeout resolution: `backend/settings/*`, `backend/infrastructure/provider_settings.py`
- Chat model factory: `backend/infrastructure/chat_model_factory.py`
- Message/media assembly + token estimate: `backend/message_builder.py`
- LangGraph StateGraph (Plan -> Act -> Observe -> Reflect): `backend/agent_graph.py`
- Agent entry point, builds graph and invokes: `backend/agent_orchestrator.py`
- Agent session builder: `backend/application/agent_session_builder.py`
- Chat use cases + cancellation flow: `backend/application/chat_use_cases.py`, `backend/domain/execution.py`
- Direct/agent streaming event generation: `backend/event_mapper.py`
- Tavily-first search facade + compact search-context formatter with temporary legacy fallback: `backend/web_search.py`
- Tavily REST client and search settings resolution: `backend/infrastructure/search/tavily_client.py`
- Shared search event emission adapter: `backend/search_provider.py`
- Search service orchestration used by chat use cases: `backend/application/search_service.py`
- LangChain tools (`web_search`/`read_url` names unchanged; default implementations now use Tavily): `backend/tools_registry.py`
- Request schema parsing (`ChatRequest`): `backend/schemas.py`
- `/api/chat` and `/api/chat/stream` compatibility handlers: `backend/chat_handlers.py`
- FastAPI gateway routes: `backend/gateway/app.py`
- Gateway admission control and queueing: `backend/gateway/admission.py`
- `send_json`, `send_sse_event`, static file serving helpers: `backend/http_utils.py`
- Public facade (`chat_once`, `stream_chat`, `cancel_chat`): `backend/nvidia_client.py`
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
- Capabilities + stream transport (AbortController support, `onDone` awaited, cancel helper): `frontend-react/src/shared/api/chatApiClient.js`
- SSE parsing (LF/CRLF tolerant): `frontend-react/src/shared/lib/sse/parseEventStream.js`
- Hooks: `frontend-react/src/hooks/*`
- Capability bootstrap and model selection: `frontend-react/src/hooks/useCapabilities.js`
- Media attachment workflow: `frontend-react/src/hooks/useAttachments.js`
- Components: `frontend-react/src/components/*`
- Message list container + scroll event boundary (memoized items): `frontend-react/src/components/MessageList.jsx`
- Markdown rendering with MathJax debounce: `frontend-react/src/components/RichBlock.jsx`
- React error boundary (app-level + per-message): `frontend-react/src/components/ErrorBoundary.jsx`
- Clipboard copy with visual feedback: `frontend-react/src/components/CopyButton.jsx`
- Frontend entry + Vercel Analytics mount: `frontend-react/src/main.jsx`
- Utilities: `frontend-react/src/utils/*`

## Tests and Fixtures

- Backend tests: `tests/test_*.py`
- Frontend unit/integration tests: `frontend-react/src/__tests__/*`
- Frontend e2e tests: `frontend-react/tests/*`
- Chat stream e2e spec: `frontend-react/tests/e2e/chat-stream.spec.ts`
- SSE mock helper: `frontend-react/tests/helpers/mockSse.ts`
- SSE fixtures: `frontend-react/tests/fixtures/sse/*`

## Deployment and Docs

- Vercel wrappers: `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`, `api/chat/cancel.py`
- Release notes: `CHANGELOG.md`
- Runtime/readme: `README.md`
- Detailed API failure lookup: `docs/assistant/error-status-matrix.md`

## Related

- Architecture rules: [`./architecture-rules.md`](./architecture-rules.md)
- Validation + release checklist: [`./validation-and-release-checklist.md`](./validation-and-release-checklist.md)

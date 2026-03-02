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
  - enabled: `qwen/qwen3.5-397b-a17b`, `z-ai/glm5`
  - disabled: `moonshotai/kimi-k2.5`

## SSE Contract

- Core events: `search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`, `error`, `done`
- Agent events: `agent_plan`, `agent_step_start`, `agent_step_end`, `tool_call`, `tool_result`, `agent_reflect`
- Every event includes `v: 1`
- Include `request_id` when available
- Error invariant: `error` must be followed by `done` with `finish_reason: "error"`

## Model Policy

- Supported:
  - `moonshotai/kimi-k2.5` (default)
  - `qwen/qwen3.5-397b-a17b`
  - `z-ai/glm5`
- Single source of truth: `backend/model_registry.py`
- If model supports reasoning and `thinking_mode=true`, stream `reasoning` events

## API Payload

- `message` (required), `history`, `model`, `web_search`, `agent_mode`, `thinking_mode`, `images`, `request_id`

## Architecture Rules

- Keep `backend/nvidia_client.py` as facade.
- Put detailed logic in extracted modules (`model_profile`, `message_builder`, `agent_graph`, `agent_orchestrator`, `event_mapper`, `search_provider`, `schemas`, `tools_registry`).
- Use `SearchProvider` for both agent and non-agent search event emission.
- Do not rename SSE events silently.
- Update tests + docs together.
- Frontend chat auto-scroll policy: follow only when user is near bottom (threshold `150px`); do not force scroll after user scrolls up.
- For Playwright SSE fixtures, normalize line endings to LF before parsing.
- Frontend session/stream updates must be isolated by `sessionId + requestId`; do not allow cross-session stream writes.
- Frontend persistence remains repository-driven; avoid coupling UI directly to storage implementation.

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
- Stream parser: `frontend-react/src/stream.js`
- Backend tests: `tests/test_*.py`
- Frontend tests: `frontend-react/src/__tests__/*`, `frontend-react/tests/*`
- Frontend e2e spec: `frontend-react/tests/e2e/chat-stream.spec.ts`
- Frontend e2e helper: `frontend-react/tests/helpers/mockSse.ts`
- Frontend SSE fixtures: `frontend-react/tests/fixtures/sse/*`
- Vercel wrappers: `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`
- Release notes: `CHANGELOG.md`

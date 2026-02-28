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

- Event types: `search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`, `error`, `done`
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
- Put detailed logic in extracted modules (`model_profile`, `message_builder`, `agent_orchestrator`, `event_mapper`, `search_provider`, `schemas`).
- Use `SearchProvider` for both agent and non-agent search event emission.
- Do not rename SSE events silently.
- Update tests + docs together.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend-react
pnpm test
pnpm run build
```

## Key Paths

- Model registry: `backend/model_registry.py`
- Model profile/runtime params: `backend/model_profile.py`
- Message assembly/token estimate: `backend/message_builder.py`
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
- Frontend hooks: `frontend-react/src/hooks/*`
- Frontend components: `frontend-react/src/components/*`
- Frontend utils: `frontend-react/src/utils/*`
- Stream parser: `frontend-react/src/stream.js`
- Backend tests: `tests/test_*.py`
- Frontend tests: `frontend-react/src/__tests__/*`, `frontend-react/tests/*`
- Vercel wrappers: `api/capabilities.py`, `api/chat.py`, `api/chat/stream.py`
- Release notes: `CHANGELOG.md`

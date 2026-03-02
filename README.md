# langchain-tryon maintenance

Repository maintenance and runbook for developers.

## 1. Runtime Baseline

- Python: `3.12+`
- Node: `22.22.0`
- pnpm: `10+`

## 2. Environment Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Frontend dependencies:

```powershell
cd frontend-react
pnpm install
```

Required env:

```env
NVIDIA_API_KEY=nvapi-your-key
PORT=8000
NVIDIA_USE_SYSTEM_PROXY=0
USER_AGENT=langchain-tryon/1.0
WEB_LOADER_TIMEOUT_SECONDS=2.0
WEB_SEARCH_TOTAL_BUDGET_SECONDS=4.0
WEB_LOADER_MAX_PAGES=3
WEB_LOADER_CONCURRENCY=3
```

## 3. Run Locally

```powershell
python server.py
```

Enable stream debug logs:

```powershell
python server.py --debug-stream
```

When enabled, the backend prints event-level summaries (`request_id`, resolved model, event type, token/reasoning length, and truncated previews).

Open `http://127.0.0.1:8000`.

## 4. Current Product Behavior

- Default chat path: `POST /api/chat/stream`
- Capabilities path: `GET /api/capabilities`
- Models:
  - `moonshotai/kimi-k2.5` (default)
  - `qwen/qwen3.5-397b-a17b`
  - `z-ai/glm5`
- Agent mode defaults:
  - qwen/glm: on (if `agent_mode` omitted)
  - kimi: off (if `agent_mode` omitted)
- Thinking mode default: `true`
- Media input: kimi only
- Search events and reasoning/token streams are shown in dedicated sections.

## 5. Streaming Event Contract

Expected SSE event types:

- `search_start`
- `search_done`
- `search_error`
- `context_usage`
- `reasoning`
- `token`
- `error`
- `done`

Every event is enriched with:

- `v: 1`
- `request_id` (if available)

Error invariant:

- `error` is always followed by `done` with `finish_reason: "error"`.

## 6. Build and Test

Backend tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Frontend build:

```powershell
cd frontend-react
pnpm run build
```

Frontend tests:

```powershell
cd frontend-react
pnpm test
pnpm test:visual
pnpm test:e2e
```

## 7. Architecture Snapshot

Backend:

- `backend/nvidia_client.py` (facade)
- `backend/model_registry.py` (capabilities source of truth)
- `backend/model_profile.py`
- `backend/message_builder.py`
- `backend/agent_orchestrator.py`
- `backend/event_mapper.py`
- `backend/search_provider.py`
- `backend/tools_registry.py`
- `backend/schemas.py`

Frontend:

- `frontend-react/src/App.jsx` (composition root)
- `frontend-react/src/hooks/*`
- `frontend-react/src/components/*`
- `frontend-react/src/stream.js`
- `frontend-react/src/utils/*`
- `frontend-react/src/app/AppProviders.jsx` (query + repository provider)
- `frontend-react/src/features/sessions/*` (session list, repository hooks)
- `frontend-react/src/features/chat/*` (stream controller, send pipeline, event mapper)
- `frontend-react/src/entities/session/*` (session domain helpers + memory repository)
- `frontend-react/src/shared/store/chatUiStore.js` (global UI/runtime store)

Deployment:

- `vercel.json`
- `api/capabilities.py`
- `api/chat.py`
- `api/chat/stream.py`

## 8. Release Notes Policy

- Use `CHANGELOG.md` as the canonical update record.
- For every non-trivial change, include:
  - scope and rationale
  - backend/frontend impact
  - API/SSE behavior changes
  - test updates and verification status

## 9. Frontend V2 Notes

- Session history is now a first-class frontend concept with title/time/preview list rendering.
- Streaming updates are isolated by `sessionId + requestId` to prevent cross-session bleed.
- SSE parser is CRLF/LF tolerant.
- Current persistence default is in-memory repository (`MemorySessionRepository`), with pluggable repository interface for IndexedDB or backend sync later.

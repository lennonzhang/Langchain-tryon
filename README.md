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
```

## 3. Run Locally

```powershell
python server.py
```

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

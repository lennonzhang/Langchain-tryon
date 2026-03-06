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
GATEWAY_MAX_CONCURRENCY=16
GATEWAY_MAX_QUEUE_SIZE=64
GATEWAY_QUEUE_TIMEOUT_SECONDS=15
MODEL_TIMEOUT_SECONDS=300
```

Non-NVIDIA provider env (optional - for Anthropic, OpenAI, Google via proxy):

```env
ANTHROPIC_API_KEY=...        # or CLAUDE_CLIENT_TOKEN_1 / CLAUDE_CLIENT_TOKEN
OPENAI_API_KEY=...           # or CODEX_TOKEN_1 / CODEX_TOKEN
GOOGLE_API_KEY=...              # or GEMINI_API_KEY_1 / GEMINI_API_KEY
ANTHROPIC_BASE_URL=
OPENAI_BASE_URL=
GOOGLE_BASE_URL=
NVIDIA_BASE_URL=
ANTHROPIC_TIMEOUT_SECONDS=
OPENAI_TIMEOUT_SECONDS=
GOOGLE_TIMEOUT_SECONDS=
NVIDIA_TIMEOUT_SECONDS=
```

Per-provider SSL verification (optional - for third-party proxies with cert issues):

```env
ANTHROPIC_SSL_VERIFY=false      # disable SSL cert verification for Anthropic requests
OPENAI_SSL_VERIFY=false         # disable SSL cert verification for OpenAI requests
GOOGLE_SSL_VERIFY=false         # disable SSL cert verification for Google requests
```

Timeout precedence:

- `<PROVIDER>_TIMEOUT_SECONDS`
- `MODEL_TIMEOUT_SECONDS`
- default `300`

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
- Cancel path: `POST /api/chat/cancel`
- Capabilities path: `GET /api/capabilities`
- Models:
  - NVIDIA: `moonshotai/kimi-k2.5`, `qwen/qwen3.5-397b-a17b`, `z-ai/glm5`
  - Anthropic: `anthropic/claude-sonnet-4-6` (via proxy)
  - OpenAI: `openai/gpt-5.3-codex` (default, via proxy)
  - Google: `google/gemini-3-pro-preview` (via proxy)
- Agent mode defaults:
  - on: qwen, glm, claude, codex, gemini (if `agent_mode` omitted)
  - off: kimi (if `agent_mode` omitted)
- Thinking mode default: `true`
- OpenAI Responses constraints:
  - omit top-level `temperature` and `top_p`
  - always include `reasoning` (`effort: "high"` / `"low"`)
- Stream/upstream error diagnostics use normalized provider detail (`provider`, `protocol`, `type`, optional `status`, `message`); SSE error frames preserve upstream `error.type` when available.
- Media input: kimi only
- Search events and reasoning/token streams are shown in dedicated sections.
- Agent reasoning is formatted into readable paragraphs using step-boundary and text heuristics during streaming.
- Markdown code blocks provide copy actions and syntax highlighting (highlighting runs after stream completion).
- `+ New Chat` enters a draft-only view (no immediate session creation).
- Switching from unsent draft to an existing session preserves draft text; first send from draft creates a real session and clears draft.
- Composer send button switches to `Stop` while the active session is streaming; when another session is streaming, send remains disabled.
- `Stop` first calls `POST /api/chat/cancel`, then aborts the local SSE request so backend cancellation can start immediately.
- `context_usage` is emitted at start and refreshed with a terminal `phase=final` update before `done`.
- Session sidebar keeps a stable responsive width on desktop/tablet and no longer resizes with long session content.
- On mobile (`<=600px`), sessions open as a left overlay drawer from the chat header `Sessions` button.

## 5. Streaming Event Contract

Request limits:

- JSON body max size: `10 MB`
- `request_id` max length: `256`

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

- `backend/gateway/app.py` (FastAPI gateway + SSE + cancel route)
- `backend/gateway/admission.py` (gateway concurrency, queue, timeout control)
- `backend/nvidia_client.py` (facade)
- `backend/model_registry.py` (env-driven catalog facade)
- `backend/model_profile.py` (factory compatibility facade)
- `backend/proxy_chat_model.py` (thin multi-provider LangChain adapter)
- `backend/provider_router.py` (registry-driven provider routing)
- `backend/provider_event_normalizer.py` (upstream error diagnostics)
- `backend/config.py` (compat facade over env/provider settings)
- `backend/domain/*` (model catalog + execution primitives)
- `backend/application/*` (chat / stream / cancel use cases)
- `backend/infrastructure/*` (provider settings, factories, protocol + transport adapters)
- `backend/message_builder.py`
- `backend/agent_graph.py` (LangGraph agent)
- `backend/agent_orchestrator.py`
- `backend/event_mapper.py`
- `backend/search_provider.py`
- `backend/tools_registry.py`
- `backend/schemas.py`

Frontend:

- `frontend-react/src/App.jsx` (composition root)
- `frontend-react/src/hooks/*`
- `frontend-react/src/components/*`
- `frontend-react/src/shared/lib/sse/parseEventStream.js`
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
- `api/chat/cancel.py`

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
- Frontend stream policy is global single in-flight request; new sends do not auto-abort running streams.
- User must explicitly stop the running session to unlock new sends; terminal handling is idempotent (first terminal signal wins).
- SSE parser is CRLF/LF tolerant.
- Current persistence default is in-memory repository (`MemorySessionRepository`), with pluggable repository interface for IndexedDB or backend sync later.

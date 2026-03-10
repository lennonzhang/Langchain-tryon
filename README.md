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
OPENAI_SSE_READ_TIMEOUT_SECONDS=600
SHUTDOWN_CANCEL_DRAIN_SECONDS=2
```

Visible model lists (optional, but required if you pin `*_MODELS` in `.env`):

```env
NVIDIA_MODELS=moonshotai/kimi-k2.5,qwen/qwen3.5-397b-a17b,qwen/qwen3.5-122b-a10b,z-ai/glm5
ANTHROPIC_MODELS=claude-sonnet-4-6
OPENAI_MODELS=gpt-5.3-codex
GOOGLE_MODELS=gemini-3-pro-preview
```

If any `*_MODELS` variable is set, the active catalog is filtered to that allowlist only. When adding a new model template, also add it to the matching env list in `.env` / deployment config if you use pinned model lists.

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
OPENAI_SSE_READ_TIMEOUT_SECONDS=
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

OpenAI Responses SSE read-idle timeout:

- `OPENAI_SSE_READ_TIMEOUT_SECONDS`
- default `600`

## 3. Run Locally

```powershell
python server.py
```

Local shutdown behavior:

- first `Ctrl+C` rejects new chat requests, cancels active streaming requests, and waits up to `SHUTDOWN_CANCEL_DRAIN_SECONDS` before exiting
- second `Ctrl+C` forces immediate exit

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
  - NVIDIA: `moonshotai/kimi-k2.5`, `qwen/qwen3.5-397b-a17b`, `qwen/qwen3.5-122b-a10b`, `z-ai/glm5`
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
  - lifecycle fallback merges repeated `response.output_item.added` snapshots for the same item
  - streaming read-idle timeout is controlled separately from the shared provider timeout
- Anthropic Messages constraints:
  - lifecycle recovery supports `message_start`, `content_block_*`, `message_delta`, and `message_stop`
  - `tool_use` is reconstructed from `input_json_delta` only when the final JSON is complete and parseable
  - `message_stop` is preferred; EOF fallback only recovers visible text or complete tool-use payloads
- Stream/upstream error diagnostics use normalized provider detail (`provider`, `protocol`, `type`, optional `status`, `message`); SSE error frames preserve upstream `error.type` when available.
- Media input: kimi only
- Search events and reasoning/token streams are shown in dedicated sections.
- Agent reasoning is formatted into readable paragraphs using step-boundary and text heuristics during streaming.
- Agent-capable models can interrupt a run with a structured clarification question:
  - the stream emits `user_input_required` (question + up to 3 options + optional free-text), then `done(finish_reason="user_input_required")`
  - the clarification card uses a violet accent theme with option buttons and an inline free-text input (when `allow_free_text` is true)
  - the previous clarification card transitions to a dimmed "Answered" state when the user submits a reply; submit is session-scoped (not blocked by other sessions streaming)
  - a `ToolMessage` is appended to agent state so the tool_call/result pair stays valid for future resumption
- Markdown code blocks provide copy actions and syntax highlighting (highlighting runs after stream completion).
- `New chat` enters a draft-only view (no immediate session creation).
- Switching from unsent draft to an existing session preserves draft text; first send from draft creates a real session and clears draft.
- Composer send button switches to `Stop` while the active session is streaming; when another session is streaming, send remains disabled.
- `Stop` first calls `POST /api/chat/cancel`, then aborts the local SSE request so backend cancellation can start immediately.
- Local `python server.py` shutdown uses the same backend cancellation path for active streaming requests before exit.
- If the capabilities payload contains no selectable models, the model selector stays visible but is disabled and shows `No models available`.
- `context_usage` is emitted at start and refreshed with a terminal `phase=final` update before `done`.
- Session sidebar keeps a stable responsive width on desktop/tablet and no longer resizes with long session content.
- On pointer-hover devices, the session delete action appears on card hover/focus and remains disabled for running sessions.
- On mobile (`<=600px`) and on narrower desktop layouts where the whole panel width is less than or equal to `2.7x` the rendered session-sidebar width, sessions open as a left overlay drawer from the chat header `Sessions` button.
- When that narrow desktop overlay mode is active above the mobile breakpoint, the chat card keeps desktop spacing but uses a reduced outer corner radius so the panel does not look oversized.

## 5. Streaming Event Contract

Request limits:

- JSON body max size: `10 MB`
- `request_id` max length: `256`
- active top-level `request_id` values must be unique:
  - `POST /api/chat` returns `409` if the same `request_id` is already active
  - `POST /api/chat/stream` emits `error` then `done(error)` for the same condition

Expected SSE event types:

- `search_start`
- `search_done`
- `search_error`
- `context_usage`
- `reasoning`
- `token`
- `error`
- `done`
- `user_input_required`

Every event is enriched with:

- `v: 1`
- `request_id` (if available)

Error invariant:

- `error` is always followed by `done` with `finish_reason: "error"`.
- clarification interrupt is emitted as `user_input_required` followed by `done` with `finish_reason: "user_input_required"`.

Common error responses:

| Endpoint | Condition | HTTP / terminal behavior |
| --- | --- | --- |
| `POST /api/chat` | invalid JSON / validation failure / missing `message` | `400` JSON error |
| `POST /api/chat` | payload too large | `413` JSON error |
| `POST /api/chat` | missing API key / server misconfiguration | `500` JSON error |
| `POST /api/chat` | active duplicate `request_id` | `409` JSON error |
| `POST /api/chat` | queue full / queue timeout / shutdown drain | `503` JSON error |
| `POST /api/chat` | upstream timeout | `504` JSON error |
| `POST /api/chat` | other upstream failure | `502` JSON error |
| `POST /api/chat/stream` | invalid JSON / validation failure / payload too large / shutdown drain | non-stream JSON error (`400` / `413` / `503`) |
| `POST /api/chat/stream` | missing API key / server misconfiguration | SSE `error` then `done(error)` |
| `POST /api/chat/stream` | queue full / queue timeout / active duplicate `request_id` | SSE `error` then `done(error)` |
| `POST /api/chat/stream` | upstream timeout / runtime failure after stream starts | SSE `error` then `done(error)` |
| `POST /api/chat/cancel` | invalid JSON / missing or invalid `request_id` | `400` JSON error |
| `POST /api/chat/cancel` | payload too large | `413` JSON error |
| `POST /api/chat/cancel` | request missing | `200` with `{"cancelled": false, "reason": "request_not_found"}` |

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

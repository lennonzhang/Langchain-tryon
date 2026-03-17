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
SEARCH_BACKEND=tavily
TAVILY_API_KEY=tvly-your-key
TAVILY_BASE_URL=https://api.tavily.com
TAVILY_TIMEOUT_SECONDS=15
TAVILY_SEARCH_DEPTH=basic
TAVILY_EXTRACT_DEPTH=basic
TAVILY_EXTRACT_TIMEOUT_SECONDS=30
TAVILY_MAX_EXTRACT_RESULTS=2
TAVILY_SSL_VERIFY=true
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

For detailed rules, see [`docs/assistant/`](docs/assistant/):

- Model + provider policy: [`docs/assistant/model-and-provider-policy.md`](docs/assistant/model-and-provider-policy.md)
- API + SSE contract: [`docs/assistant/api-and-sse-contract.md`](docs/assistant/api-and-sse-contract.md)
- Architecture rules: [`docs/assistant/architecture-rules.md`](docs/assistant/architecture-rules.md)
- Error status matrix: [`docs/assistant/error-status-matrix.md`](docs/assistant/error-status-matrix.md)

Key highlights:

- Default chat path: `POST /api/chat/stream`; default model: `openai/gpt-5.3-codex`
- Models: NVIDIA (kimi, qwen, glm), Anthropic (claude-sonnet-4-6), OpenAI (gpt-5.3-codex), Google (gemini-3-pro-preview)
- Agent mode auto-enabled for qwen/glm/claude/codex/gemini; disabled for kimi
- Search is Tavily-first by default (`SEARCH_BACKEND=tavily`)
- Agent clarification interrupts via `user_input_required` SSE event
- Session history is page-lifetime only (in-memory repository)
- Frontend stream policy: global single in-flight request; explicit user stop required

## 5. Build and Test

Use the `$code-change-verification` skill or run manually:

```powershell
# backend (repo root)
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# frontend (from frontend-react/)
pnpm test
pnpm test:e2e
pnpm run build
```

## 6. Architecture Snapshot

See [`docs/assistant/path-index.md`](docs/assistant/path-index.md) for the full path index.

Key entry points:

- Backend gateway: `backend/gateway/app.py`
- Public facade: `backend/nvidia_client.py`
- Provider routing: `backend/provider_router.py`
- Frontend root: `frontend-react/src/App.jsx`
- Stream pipeline: `frontend-react/src/features/chat/*`
- Deployment: `vercel.json`, `api/*.py`

## 7. Release Notes Policy

- Use `CHANGELOG.md` as the canonical update record.
- For every non-trivial change, include: scope and rationale, backend/frontend impact, API/SSE behavior changes, test updates.
- Use the `$docs-sync` skill to audit documentation coverage after behavior changes.

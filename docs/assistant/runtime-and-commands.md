# Runtime and Commands

**Purpose:** Canonical runtime baseline and command reference for agents and maintainers.
**When to read:** Before running locally, validating changes, or debugging environment issues.

## Runtime Baseline

- Python `3.12+`
- Node `22.22.0`
- pnpm `10+`
- Local app URL: `http://127.0.0.1:8000`

## Product Runtime Defaults

- Primary chat path: `POST /api/chat/stream`
- Cancel path: `POST /api/chat/cancel`
- One-shot path: `POST /api/chat`
- Capabilities path: `GET /api/capabilities`
- Gateway concurrency env: `GATEWAY_MAX_CONCURRENCY`
- Gateway queue env: `GATEWAY_MAX_QUEUE_SIZE`
- Gateway queue timeout env: `GATEWAY_QUEUE_TIMEOUT_SECONDS`
- Shared model timeout env: `MODEL_TIMEOUT_SECONDS`
- Provider timeout envs: `<PROVIDER>_TIMEOUT_SECONDS`
- OpenAI SSE read-idle timeout env: `OPENAI_SSE_READ_TIMEOUT_SECONDS` (default `600`)
- Search backend env: `SEARCH_BACKEND` (default `tavily`, `legacy` for deprecated fallback)
- Tavily API key env: `TAVILY_API_KEY`
- Tavily base URL env: `TAVILY_BASE_URL` (default `https://api.tavily.com`)
- Tavily search timeout env: `TAVILY_TIMEOUT_SECONDS` (default `15`)
- Tavily search depth env: `TAVILY_SEARCH_DEPTH` (default `basic`)
- Tavily extract depth env: `TAVILY_EXTRACT_DEPTH` (default `basic`)
- Tavily extract API timeout env: `TAVILY_EXTRACT_TIMEOUT_SECONDS` (default `30`)
- Tavily extract result limit env: `TAVILY_MAX_EXTRACT_RESULTS` (default `2`)
- Tavily SSL verify env: `TAVILY_SSL_VERIFY` (default `true`)
- Legacy search env fallbacks remain accepted during migration: `WEB_LOADER_TIMEOUT_SECONDS`, `WEB_SEARCH_TOTAL_BUDGET_SECONDS`, `WEB_LOADER_MAX_PAGES`, `WEB_LOADER_CONCURRENCY`
- Local shutdown drain env: `SHUTDOWN_CANCEL_DRAIN_SECONDS` (default `2`)
- Chat lifecycle log level env: `CHAT_LOG_LEVEL` (default `WARNING`; `INFO` for full lifecycle, `DEBUG` for SSE events)
- General log level fallback env: `LOG_LEVEL` (default `WARNING`)
- Chat lifecycle log file: `logs/latest.log` (overwritten each server restart)
- `thinking_mode` default: `true`
- Auto `agent_mode` when omitted:
  - enabled: qwen, glm, claude, codex, gemini
  - disabled: kimi

## Common Commands

```bash
# backend (repo root)
python server.py
python server.py --chat-log-level INFO    # enable chat lifecycle logging
python -m unittest discover -s tests -v
```

Search backend notes:

- default runtime path is Tavily Search + Tavily Extract
- `SEARCH_BACKEND=legacy` temporarily restores the deprecated DuckDuckGo + local page loader path
- `web_search` / `read_url` tool names and SSE search events remain unchanged across both paths
- Tavily timeout semantics are split:
  - `TAVILY_TIMEOUT_SECONDS` controls Tavily Search default timeout
  - `TAVILY_EXTRACT_TIMEOUT_SECONDS` controls Tavily Extract API timeout
  - `WEB_SEARCH_TOTAL_BUDGET_SECONDS` is the end-to-end search + extract budget when configured
- `WEB_LOADER_CONCURRENCY` remains a legacy compatibility knob; Tavily-backed search ignores it
- Tavily Extract passes the API-side `timeout` body field and logs request ids / response times / partial failures for troubleshooting

Local `python server.py` shutdown behavior:

- first `Ctrl+C`: reject new `/api/chat` and `/api/chat/stream` requests, cancel active streaming requests, and wait up to `SHUTDOWN_CANCEL_DRAIN_SECONDS`
- second `Ctrl+C`: force exit immediately

```bash
# frontend (from frontend-react/)
pnpm install
pnpm run dev
pnpm run build
pnpm test
pnpm test:e2e
```

## Validation

Run `$code-change-verification` or execute manually — see [`.agents/skills/code-change-verification/SKILL.md`](../../.agents/skills/code-change-verification/SKILL.md).

## Related

Deeper reference (L3):

- [Validation + release checklist](./validation-and-release-checklist.md)

Sibling rules (L2):

- [API + SSE contract](./api-and-sse-contract.md)
- [Model + provider policy](./model-and-provider-policy.md)

# CLAUDE.md

Quick operating notes for Claude Code in this repo.

## Overview

Full-stack LangChain chat app:

- Backend: FastAPI gateway + SSE/cancel routes + static serving
- Frontend: React + Vite output served from `frontend/dist`
- Features: streaming SSE, web search, reasoning stream, optional multimodal input, tool-calling agent flow

Default endpoint: `POST /api/chat/stream`.

## Common Commands

```bash
# backend (repo root)
python server.py
python -m unittest discover -s tests -v
```

```bash
# frontend (from frontend-react/)
pnpm install
pnpm run dev
pnpm run build
pnpm test
pnpm test:e2e
```

## Quick Troubleshooting

- OpenAI Responses `400`:
  - check that top-level `temperature` / `top_p` are not sent
  - check that `reasoning` is always present
- Missing stream completion:
  - verify error invariant `error` then `done(error)`
- Stop does not reduce backend work:
  - verify frontend hits `POST /api/chat/cancel` before aborting local fetch
- Cross-session stream bleed:
  - verify frontend isolation by `sessionId + requestId`
- Web page loading timeout/failure:
  - check `WEB_LOADER_TIMEOUT_SECONDS` (default `10`), `WEB_SEARCH_TOTAL_BUDGET_SECONDS` (default `15`)
  - web loading uses httpx async + trafilatura; requests+bs4 is the fallback path

## Quick Navigation (Progressive Disclosure)

IMPORTANT: Before starting any task, identify which docs below are relevant and read them first.

L2 shared rules:

- Runtime + commands: [`docs/assistant/runtime-and-commands.md`](docs/assistant/runtime-and-commands.md)
- API + SSE contract: [`docs/assistant/api-and-sse-contract.md`](docs/assistant/api-and-sse-contract.md)
- Model + provider policy: [`docs/assistant/model-and-provider-policy.md`](docs/assistant/model-and-provider-policy.md)
- Architecture rules: [`docs/assistant/architecture-rules.md`](docs/assistant/architecture-rules.md)

L3 deep index:

- Path index: [`docs/assistant/path-index.md`](docs/assistant/path-index.md)
- Validation + release checklist: [`docs/assistant/validation-and-release-checklist.md`](docs/assistant/validation-and-release-checklist.md)

## Fast Invariants

- Default model: `openai/gpt-5.3-codex`
- `thinking_mode` default: `true`
- `request_id` max length: `256`
- Auto `agent_mode` when omitted:
  - on: qwen, glm, claude, codex, gemini
  - off: kimi
- All providers must stream real SSE (no fake full-response stream)
- Do not silently rename SSE event names

## Documentation Rule

When behavior changes:

- update shared docs in `docs/assistant/*`,
- keep `AGENTS.md` and this file aligned as entry pages,
- append a detailed entry to `CHANGELOG.md`,
- update `README.md` if needed.

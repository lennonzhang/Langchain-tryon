# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack AI chat application using a Python/LangChain backend with NVIDIA AI endpoints and a React frontend. Supports streaming responses (SSE), web search, multimodal input (images/video), and thinking mode. Deployed on Vercel (serverless) or run locally via a built-in Python HTTP server.
Default chat path is streaming (`/api/chat/stream`).

## Commands

### Backend
```bash
# Run server locally (serves frontend static files + API)
python server.py

# Run all backend tests
python -m unittest discover -s tests -v

# Run a single test file
python -m unittest tests.test_nvidia_client -v
```

### Frontend (from frontend-react/)
```bash
pnpm install          # Install dependencies from pnpm-lock.yaml
pnpm run dev          # Vite dev server with hot reload
pnpm run build        # Production build -> ../frontend/dist
pnpm run preview      # Preview production build
```

Node/pnpm baseline for this repo:
```bash
node -v   # v22.22.0
pnpm -v   # 10+
```

### CI
GitHub Actions should run Python 3.12 unit tests and Node 22 frontend build on PRs to main.

## Architecture

```
Frontend (React 18 + Vite)          Backend (Python http.server)
---------------------------------------------------------------
frontend-react/src/App.jsx    ->    backend/chat_handlers.py (route handlers)
frontend-react/src/stream.js  ->    backend/http_utils.py    (SSE + static serving)
                                    backend/nvidia_client.py  (LangChain ChatNVIDIA)
                                    backend/web_search.py     (DuckDuckGo + loaders)
                                    backend/config.py         (env + model resolution)

Vercel Wrappers (api/)
----------------------
api/chat.py         -> wraps backend/chat_handlers.py
api/chat/stream.py  -> wraps backend/chat_handlers.py
```

**Data flow:** Frontend sends POST to `/api/chat/stream` with `{ message, history, model?, web_search?, agent_mode?, thinking_mode?, images? }`. Backend resolves the model, uses ReAct agentic flow for supported models by default when `agent_mode` is omitted (`qwen/qwen3.5-397b-a17b`, `z-ai/glm5`), optionally runs web search, builds LangChain messages with history (last 20), and streams SSE events (`search_start`, `search_done`, `token`, `reasoning`, `done`, `error`).

**Key design decisions:**
- Built-in `http.server.ThreadingHTTPServer` (no Flask/FastAPI)
- Frontend builds to static assets served by backend; SPA fallback routing
- Stateless: session history managed on the frontend
- Lazy LangChain imports for graceful degradation
- Web content loading fallback chain: WebBaseLoader -> requests+BS4 -> SSL-disabled retry

## Models

- `moonshotai/kimi-k2.5` (default): images, video, thinking mode (temp 1.0 with thinking, 0.6 without)
- `qwen/qwen3.5-397b-a17b`: thinking mode supported (`chat_template_kwargs.enable_thinking`), reasoning from `additional_kwargs.reasoning_content`
- `z-ai/glm5`: thinking mode only (temp 0.7 always)

Model capability rule:
- If a selected model supports reasoning, backend/frontend must expose reasoning output in stream mode.

## Environment Variables

Required: `NVIDIA_API_KEY`
Optional: `PORT` (default 8000), `NVIDIA_USE_SYSTEM_PROXY`, `NVIDIA_TIMEOUT_SECONDS` (default 300), `NVIDIA_MAX_COMPLETION_TOKENS` (default 4096, max 16384), `USER_AGENT`

## Tech Stack & Conventions

- **Python:** PEP 8, snake_case, unittest with mock, private functions prefixed `_`
- **JavaScript:** Plain JSX (no TypeScript), React hooks, camelCase, marked + DOMPurify for markdown
- **Node:** Requires 22.22.0 (or compatible 22.x patch), pnpm 10+ required
- **Python:** Requires 3.12+
- **Tests:** Located in `tests/`, covering nvidia_client, chat_handlers, and web_search modules

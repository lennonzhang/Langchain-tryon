# langchain-tryon maintenance

## Python version
Use Python 3.12 for this project.

## Node and package manager baseline
Use Node `22.22.0` and pnpm `10+` for all frontend tasks in this repository.

## 1) Create local venv (py3.12)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
`requirements.txt` includes `duckduckgo-search>=7,<8` for web search support.
It also includes:
- `langchain-community>=0.3,<0.4` (for `WebBaseLoader`)
- `beautifulsoup4>=4.12,<5` (HTML parsing fallback)

## 2) Configure env
Edit `.env`:
```env
NVIDIA_API_KEY=nvapi-your-key
PORT=8000
NVIDIA_USE_SYSTEM_PROXY=0
USER_AGENT=langchain-tryon/1.0
```

## 3) Run app
```powershell
python server.py
```
Open `http://127.0.0.1:8000`.

## 4) Frontend behavior (React + static build)
- Frontend is refactored to React (`frontend-react/`) with Vite build output to `frontend/dist/`.
- Backend serves static files from `frontend/dist` directly, so users can access frontend without running a separate frontend dev server.
- Main frontend files:
  - `frontend-react/src/App.jsx`: chat UI, streaming event handling, model/search/thinking/image controls
  - `frontend-react/src/stream.js`: SSE parser for `data:` events
  - `frontend-react/src/styles.css`: UI theme and motion effects
- Assistant streaming sections remain:
  - `Search`
  - `Context Usage`
  - `Reasoning`
  - `Answer`
- Model selector supports:
  - `moonshotai/kimi-k2.5`
  - `qwen/qwen3.5-397b-a17b`
  - `z-ai/glm5`
- Option toggles:
  - `Web Search`
  - `Thinking` (available for `k2.5`, `qwen3.5`, and `glm5`)
- Image input is available for `k2.5` only (up to 3 images).
- Rich rendering stack:
  - `marked` + `DOMPurify` for markdown
  - `MathJax` for formula rendering

## 4.1) Frontend build commands
From repository root:
```powershell
cd frontend-react
pnpm install
pnpm run build
```
Build output will be generated in `frontend/dist`.

Quick version check:
```powershell
node -v   # v22.22.0
pnpm -v   # 10+
```

## 5) LangChain client style
Backend aligns with ChatNVIDIA standard usage:
- `client = ChatNVIDIA(model="moonshotai/kimi-k2.5", api_key=..., temperature=1, top_p=1, max_completion_tokens=16384)`
- `response = client.invoke([{"role":"user","content":"..."}])`
- `qwen/qwen3.5-397b-a17b` reasoning stream style:
  - `for chunk in client.stream(msgs, chat_template_kwargs={"enable_thinking": True}): ...`
  - read `chunk.additional_kwargs["reasoning_content"]` when present

Thinking controls by model:
- `moonshotai/kimi-k2.5`:
  - request-time `chat_template_kwargs={"thinking": <bool>}`
  - temperature policy: `Thinking=1.0`, `Instant=0.6`
- `qwen/qwen3.5-397b-a17b`:
  - request-time `chat_template_kwargs={"enable_thinking": <bool>}`
  - recommended params: `temperature=0.6`, `top_p=0.95`
- `z-ai/glm5`:
  - model init `extra_body={"chat_template_kwargs":{"enable_thinking": <bool>, "clear_thinking": <inverse bool>}}`
  - reasoning stream is emitted only when `thinking_mode=true`

## 6) API behavior
- `POST /api/chat`: one-shot answer
- `POST /api/chat/stream`: SSE streaming events (`search_start`, `search_done`, `search_error`, `reasoning`, `token`, `done`, `error`)
- Default interaction mode is streaming (`/api/chat/stream`).
- Request body supports:
  - `web_search` (boolean)
  - `agent_mode` (boolean, optional; `true` requests agentic flow for supported models, `false` disables agentic flow, omitted uses model default auto behavior)
  - `thinking_mode` (boolean, default `true`)
  - `images` (array of data URLs, used by `k2.5` only)
- Agent implementation rule:
  - If a model supports reasoning, request and surface reasoning (`reasoning` SSE events) when `thinking_mode=true`.
- Agent default rule:
  - ReAct is the current agent architecture.
  - When `agent_mode` is omitted, agentic flow is enabled for `qwen/qwen3.5-397b-a17b` and `z-ai/glm5`, and disabled for `moonshotai/kimi-k2.5`.
- When `web_search=true`, backend tries DuckDuckGo search first, injects formatted results as a `system` message, then continues model generation.
- Search failure does not block model output. UI shows search error and answer stream continues.

## 7) Backend web search module
- `backend/web_search.py`
- `web_search(query, num_results=5)`: returns search result list (`title`, `url`, `snippet`) and may attach `content` when page fetch succeeds.
- `format_search_context(query, results)`: converts results into prompt-safe search context for system message injection.
- `load_webpage_content(url, max_chars=1800)`:
  - first tries `WebBaseLoader` (with timeout)
  - if loader fails, falls back to `requests + BeautifulSoup`
  - on SSL verification errors, retries once with `verify=False`
- `backend/nvidia_client.py`:
  - `_build_messages(..., search_context="")` supports search context injection.
  - `chat_once(..., enable_search=False)` supports optional web search.
  - `stream_chat(..., enable_search=False)` emits search events and then streams model output.
- `backend/chat_handlers.py` reads `web_search`/`agent_mode` from request JSON and passes them to model calls.

## 8) Usage
1. Install dependencies: `pip install -r requirements.txt`.
2. Build frontend static assets: `cd frontend-react && pnpm install && pnpm run build`.
3. Start backend server: `python server.py`.
4. Open `http://127.0.0.1:8000`.
5. Choose model/options (`Web Search`, `Thinking`) and send message.
6. Assistant panel shows: `Search` -> `Context Usage` -> `Reasoning` -> `Answer`.

## 9) Backend tests
Run:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
Current coverage includes:
- web search mapping and formatting
- WebBaseLoader fallback and SSL fallback paths
- request flag propagation in handlers (`web_search`, `agent_mode`, `thinking_mode`, `images`)
- streaming search/context-usage/reasoning/token event behavior
- `glm5` thinking on/off payload behavior

## 10) Legacy frontend backup
- Original baseline snapshot (`v0-legacy`) is kept in:
  - `legacy/original-v0/`
- Repository version policy:
  - `main`: current version (React frontend + static dist serving + backend features)
  - `legacy/original-v0`: original baseline only

## 11) GitHub CI/CD + Vercel
Added files:
- `.github/workflows/ci.yml`
- `.github/workflows/vercel-deploy.yml`
- `vercel.json`
- `api/chat.py`
- `api/chat/stream.py`

Workflow behavior:
- `CI`: runs backend unit tests and frontend build verification on PR and pushes.
- `Vercel Deploy`:
  - runs backend tests and frontend build first
  - non-main branches / PR: deploy preview
  - `main` push: deploy production

Required GitHub repository secrets:
- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

Required Vercel project environment variables:
- `NVIDIA_API_KEY`
- `NVIDIA_USE_SYSTEM_PROXY` (optional, default `0`)
- `USER_AGENT` (recommended: `langchain-tryon/1.0`)

Routing notes:
- `/` -> `frontend/dist/index.html`
- `/assets/*` -> `frontend/dist/assets/*`
- `/api/chat` -> `api/chat.py`
- `/api/chat/stream` -> `api/chat/stream.py`
- `vercel.json` also defines:
  - `installCommand`: `cd frontend-react && pnpm install --frozen-lockfile`
  - `buildCommand`: `cd frontend-react && pnpm run build`

## 12) Change log (2026-02-10)
- Frontend migrated to React + Vite (`frontend-react`), and static output is published to `frontend/dist`.
- Backend static serving updated to use `frontend/dist` with SPA fallback behavior.
- UI/UX upgraded with richer motion and improved visual hierarchy.
- CI now validates both backend tests and frontend production build.
- Vercel deployment is adapted to build React assets and route `/assets/*` + SPA fallback correctly.

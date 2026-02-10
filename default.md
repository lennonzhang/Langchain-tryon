# langchain-tryon maintenance

## Python version
Use Python 3.12 for this project.

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

## 4) Frontend behavior (current)
- Streaming chat UI is enabled by default in `frontend/index.html`.
- Model selector supports:
  - `moonshotai/kimi-k2.5`
  - `z-ai/glm4.7`
- Option toggles:
  - `Web Search`
  - `Thinking` (available for both `k2.5` and `glm4.7`)
- Image input remains available only for `k2.5` (up to 3 images).
- Assistant messages support Markdown rendering and LaTeX formulas.
- Streaming output is displayed in four sections:
  - `Search` (shown when web search is enabled)
  - `Context Usage` (estimated context usage per request)
  - `Reasoning` (shown when reasoning tokens are present)
  - `Answer` (main response body)
- Rendering pipeline:
  - `frontend/static/js/chat-controller.js`: reads model/search/thinking/image controls and handles stream events (`search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`)
  - `frontend/static/js/messages.js`: manages `Search` / `Context Usage` / `Reasoning` / `Answer` sections
  - `frontend/static/js/render.js`: Markdown parsing + sanitization + MathJax typesetting
- Control wiring:
  - `frontend/static/js/dom.js`: exposes `searchToggleEl`
  - `frontend/static/js/ui.js`: disables toggles/inputs while request is pending
  - `frontend/static/js/api.js`: sends `web_search`, `thinking_mode`, `images` in request body
- CDN assets loaded by `frontend/index.html`:
  - `marked`
  - `DOMPurify`
  - `MathJax`

## 5) LangChain client style
Backend aligns with ChatNVIDIA standard usage:
- `client = ChatNVIDIA(model="moonshotai/kimi-k2.5", api_key=..., temperature=1, top_p=1, max_completion_tokens=16384)`
- `response = client.invoke([{"role":"user","content":"..."}])`

Thinking controls by model:
- `moonshotai/kimi-k2.5`:
  - request-time `chat_template_kwargs={"thinking": <bool>}`
  - temperature policy: `Thinking=1.0`, `Instant=0.6`
- `z-ai/glm4.7`:
  - model init `extra_body={"chat_template_kwargs":{"enable_thinking": <bool>, "clear_thinking": <inverse bool>}}`
  - reasoning stream is emitted only when `thinking_mode=true`

## 6) API behavior
- `POST /api/chat`: one-shot answer
- `POST /api/chat/stream`: SSE streaming events (`search_start`, `search_done`, `search_error`, `reasoning`, `token`, `done`, `error`)
- Request body supports:
  - `web_search` (boolean)
  - `thinking_mode` (boolean, default `true`)
  - `images` (array of data URLs, used by `k2.5` only)
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
- `backend/chat_handlers.py` reads `web_search` from request JSON and passes it to model calls.

## 8) Usage
1. Install dependencies: `pip install -r requirements.txt`.
2. Start server: `python server.py`.
3. Open `http://127.0.0.1:8000`, choose model/options (`Web Search`, `Thinking`) and send message.
4. Assistant panel shows: `Search` -> `Context Usage` -> `Reasoning` -> `Answer`.

## 9) Backend tests
Run:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
Current coverage includes:
- web search mapping and formatting
- WebBaseLoader fallback and SSL fallback paths
- request flag propagation in handlers (`web_search`, `thinking_mode`, `images`)
- streaming search/context-usage/reasoning/token event behavior
- `glm4.7` thinking on/off payload behavior

## 10) Legacy frontend backup
- Original baseline snapshot (`v0-legacy`) is kept in:
  - `legacy/original-v0/`
- Repository version policy:
  - `main`: current version (web search, mobile optimization, CI/CD, Vercel deployment)
  - `legacy/original-v0`: original baseline only

## 11) GitHub CI/CD + Vercel
Added files:
- `.github/workflows/ci.yml`
- `.github/workflows/vercel-deploy.yml`
- `vercel.json`
- `api/chat.py`
- `api/chat/stream.py`

Workflow behavior:
- `CI`: runs backend unit tests on PR and pushes (`python -m unittest discover -s tests -v`).
- `Vercel Deploy`:
  - runs tests first
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
- `/` -> `frontend/index.html`
- `/static/*` -> `frontend/static/*`
- `/api/chat` -> `api/chat.py`
- `/api/chat/stream` -> `api/chat/stream.py`

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

## 2) Configure env
Edit `.env`:
```env
NVIDIA_API_KEY=nvapi-your-key
PORT=8000
NVIDIA_USE_SYSTEM_PROXY=0
```

## 3) Run app
```powershell
python server.py
```
Open `http://127.0.0.1:8000`.

## 4) Frontend behavior (current)
- Streaming chat UI is enabled by default in `frontend/index.html`.
- Assistant messages support Markdown rendering and LaTeX formulas.
- Streaming output is displayed in two sections:
  - `Reasoning` (shown when reasoning tokens are present)
  - `Answer` (main response body)
- Rendering pipeline:
  - `frontend/static/js/chat-controller.js`: receives stream events and routes partial output
  - `frontend/static/js/messages.js`: manages stream message sections
  - `frontend/static/js/render.js`: Markdown parsing + sanitization + MathJax typesetting
- CDN assets loaded by `frontend/index.html`:
  - `marked`
  - `DOMPurify`
  - `MathJax`

## 5) LangChain client style
Backend aligns with ChatNVIDIA standard usage:
- `client = ChatNVIDIA(model="moonshotai/kimi-k2.5", api_key=..., temperature=1, top_p=1, max_completion_tokens=16384)`
- `response = client.invoke([{"role":"user","content":"..."}])`

## 6) API behavior
- `POST /api/chat`: one-shot answer
- `POST /api/chat/stream`: SSE streaming events (`token`, `done`, `error`)

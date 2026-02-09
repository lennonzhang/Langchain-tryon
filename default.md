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

## 4) LangChain client style
Backend aligns with ChatNVIDIA standard usage:
- `client = ChatNVIDIA(model="moonshotai/kimi-k2.5", api_key=..., temperature=1, top_p=1, max_completion_tokens=16384)`
- `response = client.invoke([{"role":"user","content":"..."}])`

## 5) API behavior
- `POST /api/chat`: one-shot answer
- `POST /api/chat/stream`: SSE streaming events (`token`, `done`, `error`)

# langchain-tryon maintenance

## Version baseline
- `webp2` code has been copied into this repo as the migration baseline.
- Continue development on this repo for LangChain-based backend.

## 1) Create local venv
```powershell
python -m venv .venv
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

- `NVIDIA_USE_SYSTEM_PROXY=0` (default): ignore global proxy env vars.
- Set `NVIDIA_USE_SYSTEM_PROXY=1` only if your company/network requires proxy.

## 3) Run app
```powershell
python server.py
```
Open `http://127.0.0.1:8000`.

## 4) Backend architecture
- `backend/server.py`: HTTP routes
- `backend/chat_handlers.py`: chat endpoints
- `backend/config.py`: `.env` loading and API key
- `backend/nvidia_client.py`: LangChain + ChatNVIDIA calls

## 5) API behavior
- `POST /api/chat`: one-shot answer
- `POST /api/chat/stream`: SSE streaming events (`token`, `done`, `error`)

## 6) Common issues
- `KeyboardInterrupt`: manual stop (`Ctrl+C`), not a crash.
- `LangChain NVIDIA package missing`: activate venv and install `requirements.txt`.
- upstream connection refused: check proxy settings and network access.
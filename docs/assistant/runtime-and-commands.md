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
- One-shot path: `POST /api/chat`
- Capabilities path: `GET /api/capabilities`
- `thinking_mode` default: `true`
- Auto `agent_mode` when omitted:
  - enabled: qwen, glm, claude, codex, gemini
  - disabled: kimi

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

## Validation Command Set

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend-react
pnpm test
pnpm test:e2e
pnpm run build
```

## Related

Deeper reference (L3):

- [Validation + release checklist](./validation-and-release-checklist.md)

Sibling rules (L2):

- [API + SSE contract](./api-and-sse-contract.md)
- [Model + provider policy](./model-and-provider-policy.md)

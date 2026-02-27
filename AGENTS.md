# AGENTS.md

Operational guide for coding agents working in this repository.

## 1. Scope

- Apply these rules to the whole repo unless a deeper folder provides a stricter local guide.
- Keep changes minimal and task-focused.

## 2. Runtime Defaults

- Python: `3.12+`
- Node: `22.22.0`
- pnpm: `10+`
- Backend URL (local): `http://127.0.0.1:8000`

## 3. Chat/Product Defaults

- Default interaction path is streaming: `POST /api/chat/stream`.
- SSE events expected: `search_start`, `search_done`, `search_error`, `context_usage`, `reasoning`, `token`, `done`, `error`.
- `thinking_mode` defaults to `true`.
- Agent architecture defaults to ReAct when agentic flow is enabled.
- `agent_mode` defaults to auto by model when omitted: enabled for `qwen/qwen3.5-397b-a17b` and `z-ai/glm5`, disabled for `moonshotai/kimi-k2.5`.

## 4. Model Policy

Supported models:

- `moonshotai/kimi-k2.5` (default)
- `qwen/qwen3.5-397b-a17b`
- `z-ai/glm5`

Reasoning rule:

- If a model supports reasoning, the implementation must support reasoning output.
- When `thinking_mode=true`, stream and surface `reasoning_content` as SSE `reasoning` events.

Model-specific notes:

- `moonshotai/kimi-k2.5`
  - Thinking switch: pass `chat_template_kwargs={"thinking": <bool>}` in `invoke/stream`.
  - Reasoning output: read `additional_kwargs["reasoning_content"]` from response/chunks when present.
  - Token limit field: use `max_completion_tokens`.
- `qwen/qwen3.5-397b-a17b`
  - Thinking switch: pass `chat_template_kwargs={"enable_thinking": <bool>}` in `stream` (and invoke path when supported).
  - Reasoning output: read `additional_kwargs["reasoning_content"]` from response/chunks when present.
  - Token limit field: use `max_completion_tokens`.
- `z-ai/glm5`
  - Thinking switch: configure `extra_body={"chat_template_kwargs":{"enable_thinking": <bool>, "clear_thinking": <bool>}}`.
  - Reasoning output: read `additional_kwargs["reasoning_content"]` from stream chunks when present.
  - Token limit field: use `max_completion_tokens` in current backend implementation.

## 5. API Payload Contract

Request body fields used by backend handlers:

- `message` (required, string)
- `history` (array)
- `model` (optional string)
- `web_search` (optional bool)
- `agent_mode` (optional bool; `true` request agentic flow for supported models, `false` force off, omitted = model default auto)
- `thinking_mode` (optional bool, default `true`)
- `images` (optional array of data URLs)

## 6. Development Rules

- Prefer streaming-first UX and code paths.
- Preserve current event schema and do not silently rename SSE event types.
- Keep model capability checks centralized and consistent between backend and frontend.
- Update docs/tests together with behavior changes.

## 7. Validation Before Finish

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

If frontend behavior changed, rebuild:

```powershell
cd frontend-react
pnpm run build
```

If frontend behavior changed, run frontend tests:

```powershell
cd frontend-react
pnpm test
pnpm test:visual
pnpm test:e2e
```

Notes:

- `pnpm test`: Vitest unit/component tests.
- `pnpm test:visual`: Playwright visual regression (`visual-desktop` + `visual-mobile`).
- `pnpm test:e2e`: Playwright core flow tests (`e2e-desktop`).
- When dependencies changed, run `pnpm install` to refresh `pnpm-lock.yaml` before pushing.

## 8. Key Paths

- Backend model and streaming logic: `backend/nvidia_client.py`
- Backend request handlers: `backend/chat_handlers.py`
- Model resolution/config: `backend/config.py`
- React app: `frontend-react/src/App.jsx`
- Frontend Vitest config: `frontend-react/vitest.config.js`
- Frontend Playwright config: `frontend-react/playwright.config.ts`
- Frontend tests: `frontend-react/src/__tests__/*`, `frontend-react/tests/*`
- Static frontend: `frontend/index.html`, `frontend/static/js/*`

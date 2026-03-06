# AGENTS.md

Repository-level entry guide for coding agents.

## Scope

- Applies to the whole repo unless a deeper folder overrides it.
- Keep changes minimal, testable, and aligned with current architecture.

## Must-Know Constraints (Read First)

- Keep `backend/nvidia_client.py` as the public facade.
- Non-NVIDIA providers must route through `ProxyGatewayChatModel`.
- All providers must implement real SSE streaming (no fake full-response streaming).
- Do not silently rename SSE event names.
- Error flow invariant is mandatory: `error` must be followed by `done` with `finish_reason: "error"`.
- Web page loading uses `httpx.AsyncClient` + `trafilatura`; `requests`+`bs4` is the fallback. Do not reintroduce `WebBaseLoader`.
- Update tests and documentation together for behavior changes.

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

## Fast Defaults

- Primary chat path: `POST /api/chat/stream`
- One-shot path: `POST /api/chat`
- Capabilities path: `GET /api/capabilities`
- Default model: `openai/gpt-5.3-codex`
- `thinking_mode` default: `true`
- `request_id` max length: `256`
- Auto `agent_mode` when omitted: enabled for qwen/glm/claude/codex/gemini, disabled for kimi

## Documentation Update Rule

When behavior changes, update:

- shared docs under `docs/assistant/*` (single source of truth),
- this file `AGENTS.md` and `CLAUDE.md` entry links if needed,
- `CHANGELOG.md`,
- `README.md` if user-facing behavior changed.

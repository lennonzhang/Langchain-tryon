# Architecture Rules

**Purpose:** Normative architecture guardrails for backend, streaming, and frontend behavior.  
**When to read:** Before refactors, flow changes, event mapping updates, or frontend stream behavior changes.

## Backend Rules

- FastAPI is the backend gateway entrypoint.
- Keep `backend/nvidia_client.py` as a facade, not a feature bucket.
- Put detailed logic in extracted modules (full paths -> [path index](./path-index.md#backend)):
  - `model_profile`, `message_builder`, `agent_graph`, `agent_orchestrator`
- `event_mapper`, `search_provider`, `schemas`, `tools_registry`
- `proxy_chat_model`, `provider_router`, `provider_event_normalizer`
- `application/*`, `domain/*`, `infrastructure/*`, `gateway/*`
- Non-NVIDIA provider logic belongs in `ProxyGatewayChatModel` path, not in `nvidia_client.py`.
- All providers must implement real SSE streaming.
- Application-layer search orchestration belongs in `SearchService`; `SearchProvider` remains the shared event-emission adapter underneath.
- Web page loading uses `httpx.AsyncClient` (async concurrent) + `trafilatura` (text extraction); `requests`+`bs4` is the fallback. Do not reintroduce `WebBaseLoader`.
- Do not rename SSE events silently.
- Gateway admission is centralized in `backend/gateway/admission.py`; do not re-implement queueing or throttling in facade code.
- Static frontend serving must remain rooted under the frontend dist directory; preserve path traversal protection when changing gateway routes.
- Request cancellation is registry-driven:
  - frontend stop first hits `/api/chat/cancel`
  - backend cancellation is best-effort but must stop local streaming immediately
  - user stop terminates as `done(stop)`, not `error`

## Frontend Stream and Session Rules

- Auto-scroll policy: follow only when near bottom (threshold `150px`).
- Do not force scroll after user scrolls up.
- Normalize Playwright SSE fixture line endings to LF before parsing.
- Stream/session updates must be isolated by `sessionId + requestId`.
- Do not allow cross-session stream writes.
- Keep persistence repository-driven; do not couple UI directly to storage internals.
- `ErrorBoundary` wraps `<AppContent>` at top level and each `<RichBlock>` in `StreamMessage`.
- Stream requests use `AbortController`.
- App policy is global single in-flight stream; explicit user stop is required.
- No auto-preemption on new send.
- Stop control is colocated with send: composer submit button switches to `Stop` only for the active running session.
- `useSendMessage` must keep a synchronous `sendingRef` mutex to prevent double-send races.
- Retry policy: max one retry on network/5xx only if no tokens have been received.
- Terminal handling in `useSendMessage` is single-exit + idempotent (`finalizeStreamOnce`).
- First terminal signal wins among `done`, transport error, and abort.
- `useStreamController` awaits terminal callbacks (`onTransportError`, `onAborted`).
- `chatApiClient.streamChat` awaits `onDone` to avoid pending-cleanup races.
- `NEW_SESSION_KEY` is a draft-only view: it must not reuse previous session detail data.
- Unsent draft content under `NEW_SESSION_KEY` is preserved when switching to existing sessions.
- First successful send from `NEW_SESSION_KEY` must clear draft text for that key after the new session is created.
- Session sidebar uses responsive fixed width on desktop/tablet; avoid content-driven width growth.
- Mobile (`<=600px`) and narrow layouts where the whole panel width is less than or equal to `sessionSidebarWidth * 2.7` use a left overlay drawer for sessions opened from the chat header trigger.
- `RichBlock` debounces MathJax typesetting by `500ms`.
- `RichBlock` skips Prism highlighting while `streaming=true` and highlights code blocks once after stream completion (`streaming=false`).
- `MessageList` message items (`UserMessage`, `AssistantMessage`) remain `memo()`-wrapped.
- Reasoning display formatting is frontend-only: prefer `agent_step_start` boundaries and text heuristics for readability, without changing SSE event contracts.
- `context_usage` may be emitted multiple times; direct/agent flows emit a terminal `phase=final` usage event before `done(stop)`.

> Component and hook paths -> [path index: Frontend](./path-index.md#frontend).

## Change Hygiene

- Update tests and docs together for behavior changes.
- Keep behavior contracts synchronized in shared assistant docs.

## Related

Deeper reference (L3):

- [Path index](./path-index.md)
- [Validation + release checklist](./validation-and-release-checklist.md)

Sibling rules (L2):

- [API + SSE contract](./api-and-sse-contract.md)
- [Model + provider policy](./model-and-provider-policy.md)

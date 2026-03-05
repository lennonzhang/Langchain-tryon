# Architecture Rules

**Purpose:** Normative architecture guardrails for backend, streaming, and frontend behavior.  
**When to read:** Before refactors, flow changes, event mapping updates, or frontend stream behavior changes.

## Backend Rules

- Keep `backend/nvidia_client.py` as a facade, not a feature bucket.
- Put detailed logic in extracted modules (full paths → [path index](./path-index.md#backend)):
  - `model_profile`, `message_builder`, `agent_graph`, `agent_orchestrator`
  - `event_mapper`, `search_provider`, `schemas`, `tools_registry`
  - `proxy_chat_model`, `provider_router`, `provider_event_normalizer`
- Non-NVIDIA provider logic belongs in `ProxyGatewayChatModel` path, not in `nvidia_client.py`.
- All providers must implement real SSE streaming.
- Use `SearchProvider` for both agent and non-agent search event emission.
- Do not rename SSE events silently.

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
- `useSendMessage` must keep a synchronous `sendingRef` mutex to prevent double-send races.
- Retry policy: max one retry on network/5xx only if no tokens have been received.
- Terminal handling in `useSendMessage` is single-exit + idempotent (`finalizeStreamOnce`).
- First terminal signal wins among `done`, transport error, and abort.
- `useStreamController` awaits terminal callbacks (`onTransportError`, `onAborted`).
- `chatApiClient.streamChat` awaits `onDone` to avoid pending-cleanup races.
- `RichBlock` debounces MathJax typesetting by `500ms`.
- `MessageList` message items (`UserMessage`, `AssistantMessage`) remain `memo()`-wrapped.

> Component and hook paths → [path index: Frontend](./path-index.md#frontend).

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

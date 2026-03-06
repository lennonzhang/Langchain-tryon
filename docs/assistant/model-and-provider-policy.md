# Model and Provider Policy

**Purpose:** Canonical model policy, provider routing rules, and protocol constraints.  
**When to read:** Before adding/changing models, provider transport, or request body construction.

## Source of Truth

- Canonical model templates: `backend/domain/model_templates.py`
- Active env-driven catalog: `backend/domain/model_catalog.py`
- Compatibility facade for legacy callers: `backend/model_registry.py`

## Supported Models

- NVIDIA:
  - `moonshotai/kimi-k2.5`
  - `qwen/qwen3.5-397b-a17b`
  - `z-ai/glm5`
- Anthropic:
  - `anthropic/claude-sonnet-4-6`
- OpenAI:
  - `openai/gpt-5.3-codex` (default)
- Google:
  - `google/gemini-3-pro-preview`

## Default and Mode Policy

- Default model: `openai/gpt-5.3-codex`
- Auto `agent_mode` when omitted:
  - enabled: qwen, glm, claude, codex, gemini
  - disabled: kimi
- If a model supports reasoning and `thinking_mode=true`, stream `reasoning` events.

## Routing Policy

- Keep `backend/nvidia_client.py` as the facade.
- Non-NVIDIA models must route through `ProxyGatewayChatModel`.
- Routing flow is registry-driven:
  - `domain/model_catalog.py` -> `provider_router.py` -> `infrastructure/chat_model_factory.py`
  - compatibility facades remain at `model_registry.py` and `model_profile.py`

## Provider Protocols

- `anthropic_messages`
  - Endpoint: `POST /messages` (Anthropic Messages API)
  - Streaming: real SSE stream
- `openai_responses`
  - API style: OpenAI Responses API (`/responses`)
  - Streaming: real SSE stream (`stream: true` required)
  - `reasoning` field is required
- `google_generate_content`
  - Invoke endpoint: `POST /models/{model}:generateContent`
  - Stream endpoint: `POST /models/{model}:streamGenerateContent?alt=sse`
  - `thinkingConfig` in `generationConfig` controls thinking budget
  - response parts with `thought: true` carry reasoning tokens

## OpenAI Responses API Constraints

- Do not send `temperature` or `top_p` as top-level fields.
- Always include `reasoning`:
  - `effort: "high"` when `thinking_mode=true`
  - `effort: "low"` otherwise

## Proxy and Error Normalization Notes

- Proxy base URLs are configurable per provider via `<PROVIDER>_BASE_URL` env vars. A built-in default is used when unset.
- Provider credential resolution supports provider-specific env names and compatibility fallbacks (for example: `CLAUDE_CLIENT_TOKEN_1`).
- Provider timeout resolution uses:
  - `<PROVIDER>_TIMEOUT_SECONDS`
  - fallback `MODEL_TIMEOUT_SECONDS`
  - fallback default `300`
- Per-provider SSL verification can be disabled via `<PROVIDER>_SSL_VERIFY=false` (e.g. `ANTHROPIC_SSL_VERIFY=false`). This is useful when routing through third-party proxies with hostname-mismatched certificates.
- Disabled SSL verification is allowed but logged as a warning at startup/runtime resolution time.
- Upstream errors are normalized by `backend/provider_event_normalizer.py` into a consistent shape like `provider=X | protocol=Y | type=T | status=Z | message=...`.
- Provider stream (`SSE`) error frames are normalized with the same detail format; preserve upstream `error.type` when present.

## Related

Deeper reference (L3):

- [Path index](./path-index.md)

Sibling rules (L2):

- [API + SSE contract](./api-and-sse-contract.md)
- [Architecture rules](./architecture-rules.md)

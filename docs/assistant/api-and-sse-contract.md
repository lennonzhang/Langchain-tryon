# API and SSE Contract

**Purpose:** Single source of truth for request shape, limits, and streaming event contract.  
**When to read:** Before changing handlers, schemas, frontend stream parsing, or event mapping.

## Request Payload

Fields:

- `message` (required)
- `history`
- `model`
- `web_search`
- `agent_mode`
- `thinking_mode`
- `images`
- `request_id`

## Request Limits

- JSON body max size: `10 MB` (`413` if exceeded)
- `message` max length: `100000` chars (`400 ValidationError` if exceeded)
- `history` max items: `100` (silently trimmed)
- `history` items must be `{role: str, content: str}` (invalid items are filtered out)
- `images` max items: `10` (silently trimmed)
- `images` items must be strings (invalid items are filtered out)

## Core SSE Events

- `search_start`
- `search_done`
- `search_error`
- `context_usage`
- `reasoning`
- `token`
- `error`
- `done`

## Agent SSE Events

- `agent_plan`
- `agent_step_start`
- `agent_step_end`
- `tool_call`
- `tool_result`
- `agent_reflect`

## Event Envelope and Invariants

- Every event includes `v: 1`.
- Include `request_id` when available.
- Error invariant: `error` must be followed by `done` with `finish_reason: "error"`.
- Agent timeout: `600s` soft deadline; if exceeded, emit `error` then `done(error)`.
- Do not silently rename SSE event names.

## Related

Deeper reference (L3):

- [Path index](./path-index.md)

Sibling rules (L2):

- [Architecture rules](./architecture-rules.md)
- [Model + provider policy](./model-and-provider-policy.md)
- [Runtime + commands](./runtime-and-commands.md)

# API and SSE Contract

**Purpose:** Single source of truth for request shape, limits, and streaming event contract.  
**When to read:** Before changing handlers, schemas, frontend stream parsing, or event mapping.

## HTTP Endpoints

- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/chat/cancel`
- `GET /api/capabilities`

During local `python server.py` shutdown drain:

- `POST /api/chat` returns `503`
- `POST /api/chat/stream` returns `503`
- `POST /api/chat/cancel` remains available

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
- `request_id` max length: `256` chars (`400 ValidationError` if exceeded)
- `request_id` must be unique among active top-level requests:
  - `POST /api/chat` returns `409` with `error: "request_id already active"`
  - `POST /api/chat/stream` keeps the stream contract and emits `error` then `done(error)`
- `history` max items: `100` (silently trimmed)
- `history` items must be `{role: str, content: str}` (invalid items are filtered out)
- `images` max items: `10` (silently trimmed)
- `images` items must be strings (invalid items are filtered out)

## Error Responses

- `POST /api/chat`
  - validation failures return JSON errors (`400` / `413`)
  - active duplicate `request_id` returns `409`
  - gateway saturation and shutdown gate return `503`
  - upstream timeout returns `504`
  - other upstream/runtime failure returns `502`
- `POST /api/chat/stream`
  - request parsing failures return JSON errors before the stream starts
  - once streaming is established, terminal failures are reported in-band as `error` then `done(error)`
- `POST /api/chat/cancel`
  - request parsing failures return JSON errors (`400` / `413`)
  - missing requests still return `200` with `{"cancelled": false, "reason": "request_not_found"}`

Full matrix:

- [Error Status Matrix](./error-status-matrix.md)

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
- `context_usage` can appear multiple times; normal completion emits terminal `phase: "final"` before `done(stop)`.
- Error invariant: `error` must be followed by `done` with `finish_reason: "error"`.
- User-triggered stop is a normal terminal path:
  - frontend calls `POST /api/chat/cancel`
  - backend attempts to cancel the active request
  - stream ends with `done` and `finish_reason: "stop"`
- Agent timeout: `600s` soft deadline; if exceeded, emit `error` then `done(error)`.
- Do not silently rename SSE event names.

## Related

Deeper references:

- [Path index](./path-index.md)
- [Error status matrix](./error-status-matrix.md)

Sibling rules (L2):

- [Architecture rules](./architecture-rules.md)
- [Model + provider policy](./model-and-provider-policy.md)
- [Runtime + commands](./runtime-and-commands.md)

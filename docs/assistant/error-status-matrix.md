# Error Status Matrix

**Purpose:** Detailed request/response error lookup table for API callers and maintainers.  
**When to read:** When you need exact HTTP status, JSON body, or SSE terminal behavior for failure cases.

## `POST /api/chat`

| Condition | HTTP status | Body |
| --- | --- | --- |
| Invalid JSON body | `400` | `{"error": "Invalid JSON body"}` |
| Validation failure (`message`, `request_id`, etc.) | `400` | `{"error": "<validation detail>"}` |
| Missing `message` | `400` | `{"error": "message is required"}` |
| Payload too large | `413` | `{"error": "Payload too large"}` |
| Active `request_id` already in use | `409` | `{"error": "request_id already active"}` |
| Gateway queue full | `503` | `{"error": "gateway queue is full"}` |
| Gateway queue timeout | `503` | `{"error": "gateway queue timeout"}` |
| Local shutdown drain active | `503` | `{"error": "Server shutting down"}` |
| Upstream timeout | `504` | `{"error": "Upstream request timeout", "detail": "..."}` |
| Other upstream/runtime failure | `502` | `{"error": "Upstream request failed", "detail": "..."}` |

## `POST /api/chat/stream`

| Condition | HTTP status | Stream payload |
| --- | --- | --- |
| Invalid JSON body | `400` | JSON error body |
| Validation failure (`message`, `request_id`, etc.) | `400` | JSON error body |
| Missing `message` | `400` | JSON error body |
| Payload too large | `413` | JSON error body |
| Local shutdown drain active | `503` | JSON error body |
| Gateway queue full | `200` | `error` then `done(error)` |
| Gateway queue timeout | `200` | `error` then `done(error)` |
| Active `request_id` already in use | `200` | `error` then `done(error)` |
| Upstream timeout during stream | `200` | `error` then `done(error)` |
| Other upstream/runtime failure during stream | `200` | `error` then `done(error)` |

Notes:

- Stream error frames still include the SSE envelope fields such as `v: 1` and `request_id` when available.
- For streaming requests, once the SSE response is established, terminal failures are reported in-band as `error` followed by `done` with `finish_reason: "error"`.

## `POST /api/chat/cancel`

| Condition | HTTP status | Body |
| --- | --- | --- |
| Invalid JSON body | `400` | `{"error": "Invalid JSON body"}` |
| Missing `request_id` | `400` | `{"error": "request_id is required"}` |
| `request_id` too long | `400` | `{"error": "request_id: too long (...)"}` |
| Payload too large | `413` | `{"error": "Payload too large"}` |
| Request found and cancelled | `200` | `{"cancelled": true}` |
| Request not found | `200` | `{"cancelled": false, "reason": "request_not_found"}` |

## Related

- [API + SSE contract](./api-and-sse-contract.md)
- [Validation + release checklist](./validation-and-release-checklist.md)

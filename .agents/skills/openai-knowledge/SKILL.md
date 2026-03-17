---
name: openai-knowledge
description: Use when working with the OpenAI Responses API provider protocol in langchain-tryon and you need authoritative, up-to-date documentation (schemas, streaming lifecycle, limits, edge cases). This project routes OpenAI models through ProxyGatewayChatModel using the openai_responses protocol.
---

# OpenAI Knowledge

## Overview

When debugging or extending the `openai_responses` provider protocol in this project, consult the official OpenAI documentation for authoritative details on the Responses API streaming lifecycle, request shape, and constraints.

## Project context

- This project uses the OpenAI Responses API (`/responses`) for the `openai/gpt-5.3-codex` model.
- Provider protocol implementation: `backend/infrastructure/protocols/` (openai_responses)
- Key constraints documented in `docs/assistant/model-and-provider-policy.md`:
  - Do not send `temperature` or `top_p` as top-level fields.
  - Always include `reasoning` (`effort: "high"` / `"low"`).
  - Lifecycle-based reconstruction from `response.created`, `response.output_item.added`, `response.output_item.done`.
  - Dedicated SSE read-idle timeout via `OPENAI_SSE_READ_TIMEOUT_SECONDS`.

## Workflow

### 1) Check whether an OpenAI Docs MCP server is available

If `mcp__openaiDeveloperDocs__*` tools are available in your environment, use them to search and fetch exact docs.

### 2) Use MCP tools to pull exact docs

- Search first, then fetch the specific page or pages.
- Base your answer on the fetched text. Do not invent flags, field names, defaults, or limits.

### 3) If MCP is not available

- Consult https://platform.openai.com/docs for the Responses API reference.
- When in doubt, treat the project's own provider implementation code as the source of truth for how this project uses the API.

from __future__ import annotations

import json
import logging
import uuid
from urllib import error, request

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from backend.infrastructure.protocols.common import (
    detail_from_exception,
    detail_from_stream_error_event,
    messages_to_role_content,
)
from backend.infrastructure.transport.http_client import json_post, urlopen
from backend.infrastructure.transport.sse_parser import iter_sse_events
from backend.provider_event_normalizer import normalize_upstream_error, normalized_error_detail

logger = logging.getLogger(__name__)


def invoke(config, messages: list):
    mapped_messages, system_prompt = messages_to_role_content(messages)
    body = {
        "model": config.model,
        "max_tokens": config.max_completion_tokens,
        "messages": mapped_messages,
        "temperature": config.temperature,
        "top_p": config.top_p,
    }
    if system_prompt:
        body["system"] = system_prompt
    if config.bound_tools:
        body["tools"] = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
            }
            for tool in config.bound_tools
        ]
        if config.tool_choice in {"any", "auto"}:
            body["tool_choice"] = {"type": "auto"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
        "anthropic-version": "2023-06-01",
    }
    data = json_post(
        f"{config.base_url.rstrip('/')}/messages",
        headers,
        body,
        config.timeout,
        model_id=f"anthropic/{config.model}",
        ssl_verify=config.ssl_verify,
    )
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for block in data.get("content", []):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text", "")))
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                    "name": str(block.get("name") or "tool"),
                    "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                }
            )
    usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
    return AIMessage(content="".join(text_parts), tool_calls=tool_calls), {
        "usage": usage,
        "model": data.get("model", config.model),
    }


def stream(config, messages: list):
    mapped_messages, system_prompt = messages_to_role_content(messages)
    body = {
        "model": config.model,
        "max_tokens": config.max_completion_tokens,
        "messages": mapped_messages,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "stream": True,
    }
    if system_prompt:
        body["system"] = system_prompt
    if config.bound_tools:
        body["tools"] = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
            }
            for tool in config.bound_tools
        ]
        if config.tool_choice in {"any", "auto"}:
            body["tool_choice"] = {"type": "auto"}

    req = request.Request(
        f"{config.base_url.rstrip('/')}/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urlopen(req, config.timeout, ssl_verify=config.ssl_verify) as resp:
            for frame in iter_sse_events(resp):
                data_raw = frame.get("data", "")
                if not data_raw or data_raw == "[DONE]":
                    continue
                try:
                    event = json.loads(data_raw)
                except Exception:  # noqa: BLE001
                    logger.warning("Skipped malformed SSE event: %.200s", data_raw)
                    continue
                event_type = event.get("type")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if not isinstance(delta, dict):
                        continue
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                    elif delta_type == "thinking_delta":
                        thinking = delta.get("thinking")
                        if isinstance(thinking, str) and thinking:
                            yield ChatGenerationChunk(
                                message=AIMessageChunk(content="", additional_kwargs={"reasoning_content": thinking})
                            )
                elif event_type == "error":
                    raise RuntimeError(detail_from_stream_error_event(f"anthropic/{config.model}", event))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        info = normalize_upstream_error(f"anthropic/{config.model}", status=getattr(exc, "code", None), raw_body=raw)
        raise RuntimeError(normalized_error_detail(info)) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"anthropic/{config.model}", exc)) from exc

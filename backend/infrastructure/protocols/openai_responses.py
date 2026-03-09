from __future__ import annotations

import json
import logging
from urllib import error, request

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from backend.infrastructure.protocols.common import (
    detail_from_exception,
    detail_from_stream_error_event,
    messages_to_role_content,
    parse_openai_completed,
)
from backend.infrastructure.transport.http_client import urlopen
from backend.infrastructure.transport.sse_parser import iter_sse_events
from backend.provider_event_normalizer import normalize_upstream_error, normalized_error_detail

logger = logging.getLogger(__name__)


def build_body(config, messages: list) -> tuple[dict, dict[str, str]]:
    mapped_messages, system_prompt = messages_to_role_content(messages)
    input_items = mapped_messages
    if system_prompt:
        input_items = [{"role": "system", "content": system_prompt}, *input_items]

    body = {
        "model": config.model,
        "input": input_items,
        "store": False,
        "stream": True,
        "text": {"format": {"type": "text"}},
        "reasoning": {"effort": "high" if config.thinking_mode else "low", "summary": "auto"},
    }
    if config.bound_tools:
        response_tools = []
        for tool in config.bound_tools:
            schema = tool.get("openai_schema", {}) if isinstance(tool.get("openai_schema"), dict) else {}
            function_block = schema.get("function", {}) if isinstance(schema, dict) else {}
            response_tools.append(
                {
                    "type": "function",
                    "name": function_block.get("name", tool.get("name", "tool")),
                    "description": function_block.get("description", tool.get("description", "")),
                    "parameters": function_block.get(
                        "parameters",
                        tool.get("parameters", {"type": "object", "properties": {}}),
                    ),
                }
            )
        body["tools"] = response_tools
        if config.tool_choice:
            body["tool_choice"] = config.tool_choice

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }
    return body, headers


def invoke(config, messages: list):
    body, headers = build_body(config, messages)
    req = request.Request(
        f"{config.base_url.rstrip('/')}/responses",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    completed_data = None
    last_event_type = "none"
    processed_lines = 0
    try:
        with urlopen(req, config.timeout, ssl_verify=config.ssl_verify) as resp:
            for frame in iter_sse_events(resp):
                processed_lines = max(processed_lines, int(frame.get("line_count", 0)))
                data_raw = frame.get("data", "")
                if not data_raw or data_raw == "[DONE]":
                    continue
                try:
                    event = json.loads(data_raw)
                except Exception:  # noqa: BLE001
                    logger.warning("Skipped malformed SSE event: %.200s", data_raw)
                    continue
                event_type = event.get("type")
                last_event_type = str(event_type or frame.get("event") or "unknown")
                if event_type == "response.completed":
                    completed_data = event.get("response", {})
                elif event_type == "error":
                    raise RuntimeError(detail_from_stream_error_event(f"openai/{config.model}", event))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        info = normalize_upstream_error(f"openai/{config.model}", status=getattr(exc, "code", None), raw_body=raw)
        raise RuntimeError(normalized_error_detail(info)) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"openai/{config.model}", exc)) from exc

    if completed_data is None:
        raise RuntimeError(
            detail_from_exception(
                f"openai/{config.model}",
                RuntimeError(
                    "missing response.completed event "
                    f"(provider=openai model={config.model} last_event={last_event_type} lines={processed_lines})"
                ),
            )
        )

    text_parts, reasoning_parts, tool_calls, usage = parse_openai_completed(completed_data)
    additional_kwargs = {}
    reasoning_text = "\n".join(reasoning_parts).strip()
    if reasoning_text:
        additional_kwargs["reasoning_content"] = reasoning_text
    message = AIMessage(content="".join(text_parts), tool_calls=tool_calls, additional_kwargs=additional_kwargs)
    return message, {"usage": usage, "model": completed_data.get("model", config.model)}


def stream(config, messages: list):
    body, headers = build_body(config, messages)
    req = request.Request(
        f"{config.base_url.rstrip('/')}/responses",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    had_text_deltas = False
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
                if event_type == "response.output_text.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        had_text_deltas = True
                        yield ChatGenerationChunk(message=AIMessageChunk(content=delta))
                elif event_type in {"response.reasoning_summary_text.delta", "response.reasoning.delta"}:
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        yield ChatGenerationChunk(
                            message=AIMessageChunk(content="", additional_kwargs={"reasoning_content": delta})
                        )
                elif event_type == "response.completed" and not had_text_deltas:
                    response_obj = event.get("response", {})
                    if isinstance(response_obj, dict):
                        for item in response_obj.get("output", []):
                            if not isinstance(item, dict) or item.get("type") != "message":
                                continue
                            for part in item.get("content", []):
                                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                                    text = part.get("text")
                                    if isinstance(text, str) and text:
                                        yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                elif event_type == "error":
                    raise RuntimeError(detail_from_stream_error_event(f"openai/{config.model}", event))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        info = normalize_upstream_error(f"openai/{config.model}", status=getattr(exc, "code", None), raw_body=raw)
        raise RuntimeError(normalized_error_detail(info)) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"openai/{config.model}", exc)) from exc

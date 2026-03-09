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


def build_body(config, messages: list) -> tuple[dict, dict[str, str]]:
    mapped_messages, system_prompt = messages_to_role_content(messages)
    contents = []
    for item in mapped_messages:
        role = item.get("role", "user")
        google_role = "model" if role == "assistant" else "user"
        contents.append({"role": google_role, "parts": [{"text": item.get("content", "")}]})

    generation_config = {
        "temperature": config.temperature,
        "topP": config.top_p,
        "maxOutputTokens": config.max_completion_tokens,
    }
    if config.thinking_mode:
        generation_config["thinkingConfig"] = {"thinkingBudget": 8192}

    body = {
        "contents": contents,
        "generationConfig": generation_config,
    }
    if system_prompt:
        body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    if config.bound_tools:
        body["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    }
                ]
            }
            for tool in config.bound_tools
        ]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }
    return body, headers


def invoke(config, messages: list):
    body, headers = build_body(config, messages)
    data = json_post(
        f"{config.base_url.rstrip('/')}/models/{config.model}:generateContent",
        headers,
        body,
        config.timeout,
        model_id=f"google/{config.model}",
        ssl_verify=config.ssl_verify,
    )
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict] = []
    for candidate in data.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []):
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                if part.get("thought"):
                    reasoning_parts.append(text)
                else:
                    text_parts.append(text)
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                tool_calls.append(
                    {
                        "id": str(function_call.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                        "name": str(function_call.get("name") or "tool"),
                        "args": function_call.get("args") if isinstance(function_call.get("args"), dict) else {},
                    }
                )
    additional_kwargs = {}
    reasoning_text = "".join(reasoning_parts)
    if reasoning_text:
        additional_kwargs["reasoning_content"] = reasoning_text
    usage = data.get("usageMetadata", {}) if isinstance(data.get("usageMetadata"), dict) else {}
    return AIMessage(content="".join(text_parts), tool_calls=tool_calls, additional_kwargs=additional_kwargs), {
        "usage": usage,
        "model": data.get("modelVersion", config.model),
    }


def stream(config, messages: list):
    body, headers = build_body(config, messages)
    req = request.Request(
        f"{config.base_url.rstrip('/')}/models/{config.model}:streamGenerateContent?alt=sse",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, config.timeout, ssl_verify=config.ssl_verify) as resp:
            for frame in iter_sse_events(resp):
                data_raw = frame.get("data", "")
                if not data_raw or data_raw == "[DONE]":
                    continue
                try:
                    chunk_data = json.loads(data_raw)
                except Exception:  # noqa: BLE001
                    logger.warning("Skipped malformed SSE event: %.200s", data_raw)
                    continue
                if chunk_data.get("error"):
                    raise RuntimeError(detail_from_stream_error_event(f"google/{config.model}", chunk_data))
                for candidate in chunk_data.get("candidates", []):
                    if not isinstance(candidate, dict):
                        continue
                    content = candidate.get("content", {})
                    if not isinstance(content, dict):
                        continue
                    for part in content.get("parts", []):
                        if not isinstance(part, dict):
                            continue
                        text = part.get("text")
                        if not isinstance(text, str) or not text:
                            continue
                        if part.get("thought"):
                            yield ChatGenerationChunk(
                                message=AIMessageChunk(content="", additional_kwargs={"reasoning_content": text})
                            )
                        else:
                            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        info = normalize_upstream_error(f"google/{config.model}", status=getattr(exc, "code", None), raw_body=raw)
        raise RuntimeError(normalized_error_detail(info)) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"google/{config.model}", exc)) from exc

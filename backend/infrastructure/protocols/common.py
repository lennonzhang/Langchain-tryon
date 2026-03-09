from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage

from backend.message_builder import extract_text
from backend.provider_event_normalizer import normalize_upstream_error, normalized_error_detail


def detail_from_exception(model_id: str, exc: Exception) -> str:
    raw = str(exc or "").strip()
    if raw.startswith("provider=") and "protocol=" in raw:
        return raw
    info = normalize_upstream_error(model_id, raw_body=raw)
    return normalized_error_detail(info)


def detail_from_stream_error_event(
    model_id: str,
    event: dict[str, Any],
    default_message: str = "upstream stream error",
) -> str:
    raw = json.dumps(event, ensure_ascii=False)
    info = normalize_upstream_error(model_id, raw_body=raw)
    if not info.message or info.message == raw:
        nested = event.get("error")
        if isinstance(nested, dict):
            info.message = str(nested.get("message") or default_message)
        else:
            info.message = str(event.get("message") or default_message)
    return normalized_error_detail(info)


def safe_json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:  # noqa: BLE001
            return {"value": value}
    return {}


def map_role(msg: BaseMessage) -> str:
    msg_type = getattr(msg, "type", "")
    if msg_type == "system":
        return "system"
    if msg_type == "human":
        return "user"
    if msg_type == "ai":
        return "assistant"
    if msg_type == "tool":
        return "tool"
    return "user"


def messages_to_role_content(messages: list[BaseMessage]) -> tuple[list[dict[str, Any]], str]:
    mapped: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for msg in messages:
        role = map_role(msg)
        content = extract_text(getattr(msg, "content", ""))
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "") or "tool"
            content = f"Tool '{tool_name}' result: {content}"
            role = "user"
        mapped.append({"role": role, "content": content})
    return mapped, "\n\n".join(system_parts).strip()


def parse_openai_completed(data: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, Any]]:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "reasoning":
            for summary in item.get("summary", []):
                if isinstance(summary, dict):
                    text = summary.get("text")
                    if isinstance(text, str) and text:
                        reasoning_parts.append(text)
        elif item_type == "message":
            for part in item.get("content", []):
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"}:
                    text = part.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
        elif item_type in {"function_call", "tool_call"}:
            tool_calls.append(
                {
                    "id": str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                    "name": str(item.get("name") or "tool"),
                    "args": safe_json_loads(item.get("arguments")),
                }
            )
    usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
    return text_parts, reasoning_parts, tool_calls, usage

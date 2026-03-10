from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
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


@dataclass
class _AnthropicBlockState:
    index: int
    block_type: str
    text: str = ""
    thinking: str = ""
    tool_id: str = ""
    tool_name: str = ""
    tool_input: dict | None = None
    partial_json: str = ""
    stopped: bool = False


class _AnthropicStreamAccumulator:
    def __init__(self):
        self.message_started = False
        self.message_stopped = False
        self.message_meta: dict = {}
        self.message_delta: dict = {}
        self.usage: dict = {}
        self.blocks: dict[int, _AnthropicBlockState] = {}

    def add_event(self, event: dict) -> None:
        event_type = event.get("type")

        if event_type == "message_start":
            message = event.get("message")
            if isinstance(message, dict):
                self.message_started = True
                self.message_meta = {**self.message_meta, **message}
                usage = message.get("usage")
                if isinstance(usage, dict):
                    self.usage = {**self.usage, **usage}
            return

        if event_type == "message_delta":
            delta = event.get("delta")
            if isinstance(delta, dict):
                self.message_delta = {**self.message_delta, **delta}
            usage = event.get("usage")
            if isinstance(usage, dict):
                self.usage = {**self.usage, **usage}
            return

        if event_type == "message_stop":
            self.message_stopped = True
            return

        if event_type == "content_block_start":
            index = event.get("index")
            content_block = event.get("content_block")
            if not isinstance(index, int) or not isinstance(content_block, dict):
                return
            self.blocks[index] = _AnthropicBlockState(
                index=index,
                block_type=str(content_block.get("type") or ""),
                text=str(content_block.get("text") or ""),
                thinking=str(content_block.get("thinking") or ""),
                tool_id=str(content_block.get("id") or ""),
                tool_name=str(content_block.get("name") or ""),
                tool_input=content_block.get("input") if isinstance(content_block.get("input"), dict) else None,
            )
            return

        if event_type == "content_block_delta":
            index = event.get("index")
            delta = event.get("delta")
            if not isinstance(index, int) or not isinstance(delta, dict):
                return
            state = self.blocks.get(index)
            if state is None:
                return
            delta_type = delta.get("type")
            if delta_type == "text_delta" and state.block_type == "text":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    state.text += text
            elif delta_type == "thinking_delta" and state.block_type == "thinking":
                thinking = delta.get("thinking")
                if isinstance(thinking, str) and thinking:
                    state.thinking += thinking
            elif delta_type == "input_json_delta" and state.block_type == "tool_use":
                partial_json = delta.get("partial_json")
                if isinstance(partial_json, str) and partial_json:
                    state.partial_json += partial_json
            return

        if event_type == "content_block_stop":
            index = event.get("index")
            if not isinstance(index, int):
                return
            state = self.blocks.get(index)
            if state is not None:
                state.stopped = True

    def final_blocks(self, *, allow_eof_fallback: bool) -> list[dict] | None:
        if not self.message_stopped and not allow_eof_fallback:
            return None

        blocks = [self._finalize_block(state) for _, state in sorted(self.blocks.items())]
        finalized_blocks = [block for block in blocks if isinstance(block, dict)]
        if self.message_stopped:
            return finalized_blocks

        if any(block.get("type") == "text" and str(block.get("text") or "") for block in finalized_blocks):
            return finalized_blocks
        if any(block.get("type") == "tool_use" for block in finalized_blocks):
            return finalized_blocks
        return None

    def _finalize_block(self, state: _AnthropicBlockState) -> dict | None:
        if state.block_type == "text":
            return {"type": "text", "text": state.text}
        if state.block_type == "thinking":
            return {"type": "thinking", "thinking": state.thinking}
        if state.block_type == "tool_use":
            tool_input = state.tool_input
            if tool_input is None and state.partial_json:
                try:
                    parsed = json.loads(state.partial_json)
                except Exception:  # noqa: BLE001
                    parsed = None
                if isinstance(parsed, dict):
                    tool_input = parsed
            if tool_input is None:
                return None
            return {
                "type": "tool_use",
                "id": state.tool_id,
                "name": state.tool_name or "tool",
                "input": tool_input,
            }
        return None


def _parse_anthropic_content_blocks(blocks: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text", "")))
        elif block_type == "thinking":
            thinking = block.get("thinking")
            if isinstance(thinking, str) and thinking:
                reasoning_parts.append(thinking)
        elif block_type == "tool_use":
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                tool_input = {}
            tool_calls.append(
                {
                    "id": str(block.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                    "name": str(block.get("name") or "tool"),
                    "args": tool_input,
                }
            )

    return text_parts, reasoning_parts, tool_calls


def _iter_text_blocks(blocks: list[dict]):
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            yield text


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
    content_blocks = data.get("content") if isinstance(data.get("content"), list) else []
    text_parts, reasoning_parts, tool_calls = _parse_anthropic_content_blocks(content_blocks)
    usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
    additional_kwargs = {}
    reasoning_text = "\n".join(reasoning_parts).strip()
    if reasoning_text:
        additional_kwargs["reasoning_content"] = reasoning_text
    return AIMessage(content="".join(text_parts), tool_calls=tool_calls, additional_kwargs=additional_kwargs), {
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

    accumulator = _AnthropicStreamAccumulator()
    had_text_deltas = False
    emitted_final_text_snapshot = False
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
                if event_type == "error":
                    raise RuntimeError(detail_from_stream_error_event(f"anthropic/{config.model}", event))

                accumulator.add_event(event)

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if not isinstance(delta, dict):
                        continue
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            had_text_deltas = True
                            yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                    elif delta_type == "thinking_delta":
                        thinking = delta.get("thinking")
                        if isinstance(thinking, str) and thinking:
                            yield ChatGenerationChunk(
                                message=AIMessageChunk(content="", additional_kwargs={"reasoning_content": thinking})
                            )
                elif event_type == "message_stop" and not had_text_deltas and not emitted_final_text_snapshot:
                    blocks = accumulator.final_blocks(allow_eof_fallback=False) or []
                    emitted_any = False
                    for text in _iter_text_blocks(blocks):
                        yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                        emitted_any = True
                    emitted_final_text_snapshot = emitted_any
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        info = normalize_upstream_error(f"anthropic/{config.model}", status=getattr(exc, "code", None), raw_body=raw)
        raise RuntimeError(normalized_error_detail(info)) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"anthropic/{config.model}", exc)) from exc

    if not had_text_deltas and not emitted_final_text_snapshot:
        blocks = accumulator.final_blocks(allow_eof_fallback=True) or []
        for text in _iter_text_blocks(blocks):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))

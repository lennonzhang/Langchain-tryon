from __future__ import annotations

import copy
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, NoReturn

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from backend.infrastructure.protocols.common import (
    detail_from_exception,
    detail_from_stream_error_event,
    messages_to_role_content,
    parse_openai_completed,
)
from backend.infrastructure.provider_settings import resolve_openai_sse_read_timeout
from backend.infrastructure.transport.sse_parser import iter_sse_events
from backend.provider_event_normalizer import normalize_upstream_error, normalized_error_detail

logger = logging.getLogger(__name__)


@dataclass
class _OutputItemState:
    key: str
    item: dict[str, Any]
    precedence: int
    output_index: int | None
    first_seen_seq: int


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _merge_strings(
    existing: str,
    incoming: str,
    *,
    path: tuple[str, ...],
    incoming_has_priority: bool,
    incoming_higher_precedence: bool,
) -> str:
    if not incoming:
        return existing
    if not existing:
        return incoming
    field_name = path[-1] if path else ""
    if field_name == "arguments":
        if incoming_higher_precedence:
            return incoming
        if incoming_has_priority:
            return incoming if len(incoming) >= len(existing) else existing
        return existing
    if incoming_higher_precedence or incoming_has_priority:
        return incoming
    return existing


_IMMUTABLE_SCALAR_TYPES = (str, int, float, bool, type(None))


def _safe_copy(value: Any) -> Any:
    if isinstance(value, _IMMUTABLE_SCALAR_TYPES):
        return value
    return copy.deepcopy(value)


def _merge_values(
    existing: Any,
    incoming: Any,
    *,
    path: tuple[str, ...],
    incoming_has_priority: bool,
    incoming_higher_precedence: bool,
) -> Any:
    if existing is None:
        return _safe_copy(incoming)
    if incoming is None:
        return _safe_copy(existing)

    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(existing)
        for key, value in incoming.items():
            merged[key] = _merge_values(
                existing.get(key),
                value,
                path=path + (key,),
                incoming_has_priority=incoming_has_priority,
                incoming_higher_precedence=incoming_higher_precedence,
            )
        return merged

    if isinstance(existing, list) and isinstance(incoming, list):
        if not existing:
            return copy.deepcopy(incoming)
        if not incoming:
            return copy.deepcopy(existing)
        merged_list: list[Any] = []
        max_len = max(len(existing), len(incoming))
        for index in range(max_len):
            if index < len(existing) and index < len(incoming):
                merged_list.append(
                    _merge_values(
                        existing[index],
                        incoming[index],
                        path=path + ("[]",),
                        incoming_has_priority=incoming_has_priority,
                        incoming_higher_precedence=incoming_higher_precedence,
                    )
                )
            elif index < len(existing):
                merged_list.append(copy.deepcopy(existing[index]))
            else:
                merged_list.append(copy.deepcopy(incoming[index]))
        return merged_list

    if isinstance(existing, str) and isinstance(incoming, str):
        return _merge_strings(
            existing,
            incoming,
            path=path,
            incoming_has_priority=incoming_has_priority,
            incoming_higher_precedence=incoming_higher_precedence,
        )

    if incoming_higher_precedence or incoming_has_priority:
        return _safe_copy(incoming)
    return _safe_copy(existing) if _has_value(existing) else _safe_copy(incoming)


def _merge_output_items(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    *,
    incoming_has_priority: bool,
    incoming_higher_precedence: bool,
) -> dict[str, Any]:
    return _merge_values(
        existing,
        incoming,
        path=(),
        incoming_has_priority=incoming_has_priority,
        incoming_higher_precedence=incoming_higher_precedence,
    )


class _ResponsesAccumulator:
    def __init__(self):
        self.created_response: dict[str, Any] = {}
        self.completed_response: dict[str, Any] | None = None
        self._output_items: dict[str, _OutputItemState] = {}
        self._anon_counter = 0
        self._seen_counter = 0

    def add_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "response.created":
            response = event.get("response")
            if isinstance(response, dict):
                self.created_response = {**self.created_response, **response}
            return

        if event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, dict):
                self.completed_response = response
            return

        if event_type not in {"response.output_item.added", "response.output_item.done"}:
            return

        item = event.get("item")
        if not isinstance(item, dict):
            return

        key, output_index = self._resolve_identity(event, item)
        precedence = 2 if event_type == "response.output_item.done" else 1
        existing = self._output_items.get(key)
        if existing is None:
            self._output_items[key] = _OutputItemState(
                key=key,
                item=copy.deepcopy(item),
                precedence=precedence,
                output_index=output_index,
                first_seen_seq=self._next_seen_seq(),
            )
            return

        incoming_higher_precedence = precedence > existing.precedence
        merged_item = _merge_output_items(
            existing.item,
            item,
            incoming_has_priority=precedence >= existing.precedence,
            incoming_higher_precedence=incoming_higher_precedence,
        )
        self._output_items[key] = _OutputItemState(
            key=key,
            item=merged_item,
            precedence=max(existing.precedence, precedence),
            output_index=output_index if output_index is not None else existing.output_index,
            first_seen_seq=existing.first_seen_seq,
        )

    def final_response(self, default_model: str) -> dict[str, Any] | None:
        if self.completed_response is not None:
            return self.completed_response

        output_items = self.ordered_output_items()
        if not output_items:
            return None

        final_response: dict[str, Any] = {
            "model": self.created_response.get("model", default_model),
            "output": output_items,
            "usage": {},
        }
        if isinstance(self.created_response.get("id"), str):
            final_response["id"] = self.created_response["id"]
        return final_response

    def ordered_output_items(self) -> list[dict[str, Any]]:
        return [state.item for state in self._ordered_output_states()]

    def _ordered_output_states(self) -> list[_OutputItemState]:
        def sort_key(state: _OutputItemState) -> tuple[int, int]:
            if state.output_index is not None:
                return (0, state.output_index)
            return (1, state.first_seen_seq)

        return sorted(self._output_items.values(), key=sort_key)

    def _next_seen_seq(self) -> int:
        self._seen_counter += 1
        return self._seen_counter

    def _resolve_identity(self, event: dict[str, Any], item: dict[str, Any]) -> tuple[str, int | None]:
        output_index = event.get("output_index")
        if isinstance(output_index, int):
            return (f"idx:{output_index}", output_index)

        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            return (f"id:{item_id}", None)

        call_id = item.get("call_id")
        if isinstance(call_id, str) and call_id:
            return (f"call:{call_id}", None)

        self._anon_counter += 1
        return (f"anon:{self._anon_counter:08d}", None)


def _iter_output_text_entries(output_items: list[dict[str, Any]]) -> Iterator[tuple[int, str]]:
    for position, item in enumerate(output_items):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        text_parts: list[str] = []
        for part in item.get("content", []):
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                text = part.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
        combined = "".join(text_parts)
        if combined:
            yield position, combined


def _iter_output_text_chunks(response_obj: dict[str, Any]) -> Iterator[str]:
    if not isinstance(response_obj, dict):
        return
    output = response_obj.get("output", [])
    if not isinstance(output, list):
        return
    for _, text in _iter_output_text_entries(output):
        yield text


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _iter_incremental_snapshot_text(
    output_items: list[dict[str, Any]],
    sent_text_by_position: dict[int, str],
) -> Iterator[str]:
    for position, text in _iter_output_text_entries(output_items):
        previous = sent_text_by_position.get(position, "")
        if text == previous:
            continue
        if previous and text.startswith(previous):
            delta = text[len(previous) :]
        elif previous:
            delta = text[_common_prefix_length(previous, text) :]
        else:
            delta = text
        sent_text_by_position[position] = text
        if delta:
            yield delta


def _build_timeout(config) -> httpx.Timeout:
    read_timeout = resolve_openai_sse_read_timeout()
    return httpx.Timeout(
        timeout=config.timeout,
        connect=config.timeout,
        read=read_timeout,
        write=config.timeout,
        pool=config.timeout,
    )


def _iter_httpx_lines(response: httpx.Response) -> Iterator[bytes]:
    for line in response.iter_lines():
        if isinstance(line, bytes):
            yield line
        else:
            yield line.encode("utf-8")


@contextmanager
def _post_responses_sse(config, body: dict[str, Any], headers: dict[str, str]):
    timeout = _build_timeout(config)
    with httpx.Client(timeout=timeout, verify=config.ssl_verify) as client:
        with client.stream(
            "POST",
            f"{config.base_url.rstrip('/')}/responses",
            json=body,
            headers=headers,
        ) as response:
            response.raise_for_status()
            yield _iter_httpx_lines(response)


def _read_http_error_body(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    try:
        return response.text
    except Exception:  # noqa: BLE001
        try:
            return response.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return ""


def _raise_timeout_error(exc: BaseException) -> NoReturn:
    message = str(exc).strip() or "The read operation timed out"
    raise TimeoutError(message) from exc


def build_body(config, messages: list) -> tuple[dict[str, Any], dict[str, str]]:
    mapped_messages, system_prompt = messages_to_role_content(messages)
    input_items = mapped_messages
    if system_prompt:
        input_items = [{"role": "system", "content": system_prompt}, *input_items]

    body: dict[str, Any] = {
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
    last_event_type = "none"
    processed_lines = 0
    accumulator = _ResponsesAccumulator()
    try:
        with _post_responses_sse(config, body, headers) as raw_lines:
            for frame in iter_sse_events(raw_lines):
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
                if event_type == "error":
                    raise RuntimeError(detail_from_stream_error_event(f"openai/{config.model}", event))
                accumulator.add_event(event)
    except httpx.HTTPStatusError as exc:
        raw = _read_http_error_body(exc)
        info = normalize_upstream_error(
            f"openai/{config.model}",
            status=getattr(exc.response, "status_code", None),
            raw_body=raw,
        )
        raise RuntimeError(normalized_error_detail(info)) from exc
    except httpx.TimeoutException as exc:
        _raise_timeout_error(exc)
    except TimeoutError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"openai/{config.model}", exc)) from exc

    completed_data = accumulator.final_response(config.model)
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
    had_text_deltas = False
    accumulator = _ResponsesAccumulator()
    sent_text_by_position: dict[int, str] = {}
    try:
        with _post_responses_sse(config, body, headers) as raw_lines:
            for frame in iter_sse_events(raw_lines):
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
                    raise RuntimeError(detail_from_stream_error_event(f"openai/{config.model}", event))

                accumulator.add_event(event)

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
                elif (
                    event_type in {"response.output_item.added", "response.output_item.done", "response.completed"}
                    and not had_text_deltas
                ):
                    final_response = accumulator.final_response(config.model)
                    if final_response is not None:
                        output = final_response.get("output", [])
                        if isinstance(output, list):
                            for text in _iter_incremental_snapshot_text(output, sent_text_by_position):
                                yield ChatGenerationChunk(message=AIMessageChunk(content=text))
    except httpx.HTTPStatusError as exc:
        raw = _read_http_error_body(exc)
        info = normalize_upstream_error(
            f"openai/{config.model}",
            status=getattr(exc.response, "status_code", None),
            raw_body=raw,
        )
        raise RuntimeError(normalized_error_detail(info)) from exc
    except httpx.TimeoutException as exc:
        _raise_timeout_error(exc)
    except TimeoutError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(detail_from_exception(f"openai/{config.model}", exc)) from exc

    if not had_text_deltas:
        final_response = accumulator.final_response(config.model)
        if final_response is not None:
            output = final_response.get("output", [])
            if isinstance(output, list):
                for text in _iter_incremental_snapshot_text(output, sent_text_by_position):
                    yield ChatGenerationChunk(message=AIMessageChunk(content=text))

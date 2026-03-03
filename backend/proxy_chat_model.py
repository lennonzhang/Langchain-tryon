"""LangChain chat model adapter for proxy APIs defined in api_examples.py."""

from __future__ import annotations

import json
import uuid
from typing import Any, Iterator, Sequence
from urllib import error, request

from pydantic import Field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from .message_builder import extract_text
from .provider_event_normalizer import normalize_upstream_error, normalized_error_detail

_ERROR_PREVIEW_LIMIT = 200


def _detail_from_exception(model_id: str, exc: Exception) -> str:
    """Normalize non-HTTP exceptions into provider-tagged detail."""
    raw = str(exc or "").strip()
    if raw.startswith("provider=") and "protocol=" in raw:
        return raw
    info = normalize_upstream_error(model_id, raw_body=raw)
    return normalized_error_detail(info)


def _json_post(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_s: float,
    model_id: str = "",
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            raw_bytes = resp.read()
            raw_text = raw_bytes.decode("utf-8", errors="ignore")
            if not raw_text.strip():
                raise RuntimeError("empty upstream body")
            try:
                parsed = json.loads(raw_text)
            except Exception as parse_exc:  # noqa: BLE001
                preview = raw_text[:_ERROR_PREVIEW_LIMIT]
                raise RuntimeError(f"non-json upstream body: {preview}") from parse_exc
            if not isinstance(parsed, dict):
                raise RuntimeError(f"non-json upstream body: {str(parsed)[:_ERROR_PREVIEW_LIMIT]}")
            return parsed
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        if model_id:
            info = normalize_upstream_error(model_id, status=getattr(exc, "code", None), raw_body=raw)
            raise RuntimeError(normalized_error_detail(info)) from exc
        raise RuntimeError(raw) from exc
    except Exception as exc:  # noqa: BLE001
        if model_id:
            raise RuntimeError(_detail_from_exception(model_id, exc)) from exc
        raise


def _iter_sse_events(resp) -> Iterator[dict[str, Any]]:
    """Parse SSE stream and yield buffered events.

    Supports multi-line ``data:`` and optional ``event:`` fields.
    """
    event_name = ""
    data_parts: list[str] = []
    line_count = 0

    def _flush():
        nonlocal event_name, data_parts
        if not event_name and not data_parts:
            return None
        data_raw = "\n".join(data_parts).strip()
        item = {"event": event_name or "message", "data": data_raw, "line_count": line_count}
        event_name = ""
        data_parts = []
        return item

    for raw_line in resp:
        line_count += 1
        line = raw_line.decode("utf-8", errors="ignore").rstrip("\r\n")
        if not line.strip():
            flushed = _flush()
            if flushed is not None:
                yield flushed
            continue

        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue

        if line.startswith("data:"):
            # Some gateways omit the blank-line separator between events.
            # In that case, treat each top-level data line as a separate event
            # when no explicit `event:` type is active.
            if data_parts and not event_name:
                flushed = _flush()
                if flushed is not None:
                    yield flushed
            data_parts.append(line[5:].lstrip())
            continue

    flushed = _flush()
    if flushed is not None:
        yield flushed


def _map_role(msg: BaseMessage) -> str:
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


def _messages_to_role_content(messages: list[BaseMessage]) -> tuple[list[dict[str, Any]], str]:
    mapped: list[dict[str, Any]] = []
    system_parts: list[str] = []

    for msg in messages:
        role = _map_role(msg)
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


def _safe_json_loads(value: Any) -> dict[str, Any]:
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


class ProxyGatewayChatModel(BaseChatModel):
    """Chat model over provider proxy HTTP endpoints."""

    provider: str
    model: str
    api_key: str
    base_url: str
    timeout: float = 60.0
    temperature: float = 0.7
    top_p: float = 1.0
    max_completion_tokens: int = 1024
    thinking_mode: bool = True
    bound_tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: str | None = None

    @property
    def _llm_type(self) -> str:
        return f"proxy_{self.provider}"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        _ = kwargs
        schemas: list[dict[str, Any]] = []
        for tool in tools:
            openai_schema = convert_to_openai_tool(tool)
            function_block = openai_schema.get("function", {})
            schemas.append(
                {
                    "name": function_block.get("name", "tool"),
                    "description": function_block.get("description", ""),
                    "parameters": function_block.get("parameters", {"type": "object", "properties": {}}),
                    "openai_schema": openai_schema,
                }
            )
        return self.model_copy(update={"bound_tools": schemas, "tool_choice": tool_choice})

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        _ = (stop, run_manager, kwargs)
        if self.provider == "anthropic":
            message, llm_output = self._invoke_anthropic(messages)
        elif self.provider == "openai":
            message, llm_output = self._invoke_openai(messages)
        elif self.provider == "google":
            message, llm_output = self._invoke_google(messages)
        else:
            raise RuntimeError(f"Unsupported proxy provider: {self.provider}")

        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output=llm_output,
        )

    def _stream(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        _ = (stop, run_manager, kwargs)
        if self.provider == "openai":
            yield from self._stream_openai(messages)
        elif self.provider == "anthropic":
            yield from self._stream_anthropic(messages)
        elif self.provider == "google":
            yield from self._stream_google(messages)
        else:
            raise RuntimeError(f"Unsupported proxy provider: {self.provider}")

    def _invoke_anthropic(self, messages: list[BaseMessage]) -> tuple[AIMessage, dict[str, Any]]:
        mapped_messages, system_prompt = _messages_to_role_content(messages)
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_completion_tokens,
            "messages": mapped_messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if system_prompt:
            body["system"] = system_prompt
        if self.bound_tools:
            body["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in self.bound_tools
            ]
            if self.tool_choice in {"any", "auto"}:
                body["tool_choice"] = {"type": "auto"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "anthropic-version": "2023-06-01",
        }

        data = _json_post(f"{self.base_url.rstrip('/')}/messages", headers, body, self.timeout, model_id=f"anthropic/{self.model}")
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in data.get("content", []):
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text", "")))
            if btype == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                        "name": str(block.get("name") or "tool"),
                        "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                    }
                )

        message = AIMessage(content="".join(text_parts), tool_calls=tool_calls)
        usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
        return message, {"usage": usage, "model": data.get("model", self.model)}

    def _stream_anthropic(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
        """Stream via Anthropic Messages API SSE.

        SSE event types:
          message_start         → metadata
          content_block_start   → new block (text / tool_use / thinking)
          content_block_delta   → text_delta / thinking_delta / input_json_delta
          content_block_stop    → block end
          message_delta         → stop_reason, usage
          message_stop          → stream end
          error                 → upstream error
        """
        mapped_messages, system_prompt = _messages_to_role_content(messages)
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_completion_tokens,
            "messages": mapped_messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt
        if self.bound_tools:
            body["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in self.bound_tools
            ]
            if self.tool_choice in {"any", "auto"}:
                body["tool_choice"] = {"type": "auto"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "anthropic-version": "2023-06-01",
        }
        payload = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url.rstrip('/')}/messages",
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                for frame in _iter_sse_events(resp):
                    data_raw = frame.get("data", "")
                    if not data_raw or data_raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_raw)
                    except Exception:  # noqa: BLE001
                        continue

                    etype = event.get("type")
                    if etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if not isinstance(delta, dict):
                            continue
                        dtype = delta.get("type")
                        if dtype == "text_delta":
                            text = delta.get("text")
                            if isinstance(text, str) and text:
                                yield ChatGenerationChunk(message=AIMessageChunk(content=text))
                        elif dtype == "thinking_delta":
                            thinking = delta.get("thinking")
                            if isinstance(thinking, str) and thinking:
                                yield ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content="",
                                        additional_kwargs={"reasoning_content": thinking},
                                    ),
                                )
                    elif etype == "error":
                        err = event.get("error", {}) if isinstance(event.get("error"), dict) else {}
                        msg = str(err.get("message") or "upstream stream error")
                        raise RuntimeError(msg)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            info = normalize_upstream_error(
                f"anthropic/{self.model}",
                status=getattr(exc, "code", None),
                raw_body=raw,
            )
            raise RuntimeError(normalized_error_detail(info)) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_detail_from_exception(f"anthropic/{self.model}", exc)) from exc

    def _build_openai_body(self, messages: list[BaseMessage]) -> tuple[dict[str, Any], dict[str, str]]:
        """Build request body and headers shared by invoke and stream paths."""
        mapped_messages, system_prompt = _messages_to_role_content(messages)
        input_items = mapped_messages
        if system_prompt:
            input_items = [{"role": "system", "content": system_prompt}, *input_items]

        body: dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "store": False,
            "stream": True,  # proxy requires stream=true
            "text": {"format": {"type": "text"}},
        }
        if self.thinking_mode:
            body["reasoning"] = {"effort": "high", "summary": "auto"}
        else:
            body["reasoning"] = {"effort": "low", "summary": "auto"}
        if self.bound_tools:
            response_tools = []
            for t in self.bound_tools:
                schema = t.get("openai_schema", {})
                function_block = schema.get("function", {}) if isinstance(schema, dict) else {}
                response_tools.append(
                    {
                        "type": "function",
                        "name": function_block.get("name", t.get("name", "tool")),
                        "description": function_block.get("description", t.get("description", "")),
                        "parameters": function_block.get(
                            "parameters",
                            t.get("parameters", {"type": "object", "properties": {}}),
                        ),
                    }
                )
            body["tools"] = response_tools
            if self.tool_choice:
                body["tool_choice"] = self.tool_choice

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        return body, headers

    @staticmethod
    def _parse_openai_completed(data: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, Any]]:
        """Extract text, reasoning, tool_calls, and usage from a completed response."""
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for item in data.get("output", []):
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "reasoning":
                for summary in item.get("summary", []):
                    if isinstance(summary, dict):
                        text = summary.get("text")
                        if isinstance(text, str) and text:
                            reasoning_parts.append(text)
            elif itype == "message":
                for part in item.get("content", []):
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype in {"output_text", "text"}:
                        ptxt = part.get("text")
                        if isinstance(ptxt, str):
                            text_parts.append(ptxt)
            elif itype in {"function_call", "tool_call"}:
                tool_calls.append(
                    {
                        "id": str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                        "name": str(item.get("name") or "tool"),
                        "args": _safe_json_loads(item.get("arguments")),
                    }
                )

        usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
        return text_parts, reasoning_parts, tool_calls, usage

    def _invoke_openai(self, messages: list[BaseMessage]) -> tuple[AIMessage, dict[str, Any]]:
        body, headers = self._build_openai_body(messages)
        url = f"{self.base_url.rstrip('/')}/responses"

        # Proxy requires stream=true; consume SSE and aggregate the completed response.
        payload = json.dumps(body).encode("utf-8")
        req = request.Request(url, data=payload, headers=headers, method="POST")
        completed_data: dict[str, Any] | None = None
        last_event_type = "none"
        processed_lines = 0
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                for frame in _iter_sse_events(resp):
                    processed_lines = max(processed_lines, int(frame.get("line_count", 0)))
                    data_raw = frame.get("data", "")
                    if not data_raw or data_raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_raw)
                    except Exception:  # noqa: BLE001
                        continue
                    etype = event.get("type")
                    last_event_type = str(etype or frame.get("event") or "unknown")
                    if etype == "response.completed":
                        completed_data = event.get("response", {})
                    elif etype == "error":
                        err = event.get("error", {}) if isinstance(event.get("error"), dict) else {}
                        raise RuntimeError(str(err.get("message") or "upstream error"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            info = normalize_upstream_error(f"openai/{self.model}", status=getattr(exc, "code", None), raw_body=raw)
            raise RuntimeError(normalized_error_detail(info)) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_detail_from_exception(f"openai/{self.model}", exc)) from exc

        if completed_data is None:
            raise RuntimeError(
                _detail_from_exception(
                    f"openai/{self.model}",
                    RuntimeError(
                        "missing response.completed event "
                        f"(provider=openai model={self.model} last_event={last_event_type} lines={processed_lines})",
                    ),
                )
            )

        text_parts, reasoning_parts, tool_calls, usage = self._parse_openai_completed(completed_data)

        additional_kwargs: dict[str, Any] = {}
        reasoning_text = "\n".join(reasoning_parts).strip()
        if reasoning_text:
            additional_kwargs["reasoning_content"] = reasoning_text

        message = AIMessage(content="".join(text_parts), tool_calls=tool_calls, additional_kwargs=additional_kwargs)
        return message, {"usage": usage, "model": completed_data.get("model", self.model)}

    def _stream_openai(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
        body, headers = self._build_openai_body(messages)
        payload = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=payload,
            headers=headers,
            method="POST",
        )

        had_text_deltas = False
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                for frame in _iter_sse_events(resp):
                    data_raw = frame.get("data", "")
                    if not data_raw or data_raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_raw)
                    except Exception:  # noqa: BLE001
                        continue

                    etype = event.get("type")
                    if etype == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            had_text_deltas = True
                            yield ChatGenerationChunk(message=AIMessageChunk(content=delta))
                    elif etype in {"response.reasoning_summary_text.delta", "response.reasoning.delta"}:
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            yield ChatGenerationChunk(
                                message=AIMessageChunk(
                                    content="",
                                    additional_kwargs={"reasoning_content": delta},
                                ),
                            )
                    elif etype == "response.completed":
                        if not had_text_deltas:
                            # Fallback: emit text from completed response only when no deltas were received.
                            response_obj = event.get("response", {})
                            if isinstance(response_obj, dict):
                                for item in response_obj.get("output", []):
                                    if not isinstance(item, dict) or item.get("type") != "message":
                                        continue
                                    for part in item.get("content", []):
                                        if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                                            txt = part.get("text")
                                            if isinstance(txt, str) and txt:
                                                yield ChatGenerationChunk(message=AIMessageChunk(content=txt))
                    elif etype == "error":
                        err = event.get("error", {}) if isinstance(event.get("error"), dict) else {}
                        msg = str(err.get("message") or "upstream stream error")
                        raise RuntimeError(msg)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            info = normalize_upstream_error(
                f"openai/{self.model}",
                status=getattr(exc, "code", None),
                raw_body=raw,
            )
            raise RuntimeError(normalized_error_detail(info)) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_detail_from_exception(f"openai/{self.model}", exc)) from exc

    def _invoke_google(self, messages: list[BaseMessage]) -> tuple[AIMessage, dict[str, Any]]:
        mapped_messages, system_prompt = _messages_to_role_content(messages)
        contents = []
        for item in mapped_messages:
            role = item.get("role", "user")
            g_role = "model" if role == "assistant" else "user"
            contents.append({"role": g_role, "parts": [{"text": item.get("content", "")}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "topP": self.top_p,
                "maxOutputTokens": self.max_completion_tokens,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if self.bound_tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                        }
                    ]
                }
                for t in self.bound_tools
            ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url.rstrip('/')}/models/{self.model}:generateContent"
        data = _json_post(url, headers, body, self.timeout, model_id=f"google/{self.model}")

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for candidate in data.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            for part in content.get("parts", []):
                if not isinstance(part, dict):
                    continue
                if isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
                function_call = part.get("functionCall")
                if isinstance(function_call, dict):
                    tool_calls.append(
                        {
                            "id": str(function_call.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                            "name": str(function_call.get("name") or "tool"),
                            "args": function_call.get("args") if isinstance(function_call.get("args"), dict) else {},
                        }
                    )

        usage = data.get("usageMetadata", {}) if isinstance(data.get("usageMetadata"), dict) else {}
        return AIMessage(content="".join(text_parts), tool_calls=tool_calls), {
            "usage": usage,
            "model": data.get("modelVersion", self.model),
        }

    def _stream_google(self, messages: list[BaseMessage]) -> Iterator[ChatGenerationChunk]:
        """Stream via Google streamGenerateContent SSE.

        Endpoint: POST /models/{model}:streamGenerateContent?alt=sse
        Each SSE data line is a partial response with candidates[].content.parts[].text.
        """
        mapped_messages, system_prompt = _messages_to_role_content(messages)
        contents = []
        for item in mapped_messages:
            role = item.get("role", "user")
            g_role = "model" if role == "assistant" else "user"
            contents.append({"role": g_role, "parts": [{"text": item.get("content", "")}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "topP": self.top_p,
                "maxOutputTokens": self.max_completion_tokens,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if self.bound_tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                        }
                    ]
                }
                for t in self.bound_tools
            ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = json.dumps(body).encode("utf-8")
        url = f"{self.base_url.rstrip('/')}/models/{self.model}:streamGenerateContent?alt=sse"
        req = request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                for frame in _iter_sse_events(resp):
                    data_raw = frame.get("data", "")
                    if not data_raw or data_raw == "[DONE]":
                        continue
                    try:
                        chunk_data = json.loads(data_raw)
                    except Exception:  # noqa: BLE001
                        continue

                    # Error response
                    if chunk_data.get("error"):
                        err = chunk_data["error"]
                        msg = str(err.get("message") or "upstream stream error") if isinstance(err, dict) else str(err)
                        raise RuntimeError(msg)

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
                            if isinstance(text, str) and text:
                                yield ChatGenerationChunk(message=AIMessageChunk(content=text))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            info = normalize_upstream_error(
                f"google/{self.model}",
                status=getattr(exc, "code", None),
                raw_body=raw,
            )
            raise RuntimeError(normalized_error_detail(info)) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_detail_from_exception(f"google/{self.model}", exc)) from exc

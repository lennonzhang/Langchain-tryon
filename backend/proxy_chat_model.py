"""Thin LangChain adapter over provider-specific protocol clients."""

from __future__ import annotations

from typing import Any, Sequence
from urllib import request

from pydantic import Field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from backend.infrastructure.protocols import anthropic_messages, google_generate_content, openai_responses
from backend.infrastructure.protocols.common import (
    detail_from_exception as _detail_from_exception,
    messages_to_role_content as _messages_to_role_content,
    parse_openai_completed,
    safe_json_loads as _safe_json_loads,
)
from backend.infrastructure.transport.http_client import json_post as _json_post, urlopen
from backend.infrastructure.transport.sse_parser import iter_sse_events as _iter_sse_events

logger = anthropic_messages.logger


class ProxyGatewayChatModel(BaseChatModel):
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
    ssl_verify: bool = True

    def _urlopen(self, req, timeout):
        return urlopen(req, timeout, ssl_verify=self.ssl_verify)

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
            message, llm_output = anthropic_messages.invoke(self, messages)
        elif self.provider == "openai":
            message, llm_output = openai_responses.invoke(self, messages)
        elif self.provider == "google":
            message, llm_output = google_generate_content.invoke(self, messages)
        else:
            raise RuntimeError(f"Unsupported proxy provider: {self.provider}")

        return ChatResult(generations=[ChatGeneration(message=message)], llm_output=llm_output)

    def _stream(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any):
        _ = (stop, run_manager, kwargs)
        if self.provider == "anthropic":
            yield from anthropic_messages.stream(self, messages)
        elif self.provider == "openai":
            yield from openai_responses.stream(self, messages)
        elif self.provider == "google":
            yield from google_generate_content.stream(self, messages)
        else:
            raise RuntimeError(f"Unsupported proxy provider: {self.provider}")

    @staticmethod
    def _parse_openai_completed(data: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, Any]]:
        return parse_openai_completed(data)


__all__ = [
    "ProxyGatewayChatModel",
    "_detail_from_exception",
    "_iter_sse_events",
    "_json_post",
    "_messages_to_role_content",
    "_safe_json_loads",
]

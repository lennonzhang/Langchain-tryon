"""Facade module - public API for chat_once / stream_chat."""

from __future__ import annotations

import os

from backend.application.chat_use_cases import (
    CancelChatUseCase,
    ChatOnceUseCase,
    ChatUseCaseDependencies,
    StreamChatUseCase,
    should_use_agentic_flow as _should_use_agentic_flow,
)
from backend.config import resolve_model
from backend.domain.execution import CancellationRegistry
from backend.infrastructure.chat_model_factory import chat_model_factory as _chat_model_factory
from backend.infrastructure.chat_model_factory import output_tokens, proxy_env_guard as _proxy_env_guard
from backend.infrastructure.chat_model_factory import stream_or_invoke_kwargs as _stream_or_invoke_kwargs
from backend.message_builder import (
    build_messages as _build_messages,
    build_user_content as _build_user_content,
    context_usage_payload as _context_usage_payload,
    estimate_tokens_from_messages as _estimate_tokens_from_messages,
    extract_text as _extract_text,
    history_as_text as _history_as_text,
    normalize_image_data_urls as _normalize_image_data_urls,
    normalize_media_data_urls as _normalize_media_data_urls,
)
from backend.provider_router import build_routed_chat_model as _build_chat_model
from backend.search_provider import SearchProvider

from .agent_orchestrator import run_agent as _run_langchain_agent

_REGISTRY = CancellationRegistry()


def _supports_thinking(model: str) -> bool:
    from backend.domain.model_catalog import catalog

    return catalog.supports(model, "thinking")


def _supports_images(model: str) -> bool:
    from backend.domain.model_catalog import catalog

    return catalog.supports(model, "media")


def _run_web_search(
    message: str,
    num_results: int = 5,
    include_page_content: bool = True,
    page_timeout_s: float | None = None,
    total_budget_s: float | None = None,
    max_pages: int | None = None,
    concurrency: int | None = None,
):
    from .web_search import format_search_context, web_search

    def _float_from_env(*names: str) -> float | None:
        for name in names:
            raw = os.getenv(name, "").strip()
            if not raw:
                continue
            try:
                return float(raw)
            except ValueError:
                continue
        return None

    def _int_from_env(*names: str) -> int | None:
        for name in names:
            raw = os.getenv(name, "").strip()
            if not raw:
                continue
            try:
                return int(raw)
            except ValueError:
                continue
        return None

    resolved_page_timeout = page_timeout_s
    if resolved_page_timeout is None:
        resolved_page_timeout = _float_from_env(
            "TAVILY_EXTRACT_TIMEOUT_SECONDS",
            "WEB_LOADER_TIMEOUT_SECONDS",
        )

    resolved_total_budget = total_budget_s
    if resolved_total_budget is None:
        resolved_total_budget = _float_from_env(
            "WEB_SEARCH_TOTAL_BUDGET_SECONDS",
        )

    resolved_max_pages = max_pages
    if resolved_max_pages is None:
        resolved_max_pages = _int_from_env(
            "TAVILY_MAX_EXTRACT_RESULTS",
            "WEB_LOADER_MAX_PAGES",
        )

    resolved_concurrency = concurrency
    if resolved_concurrency is None:
        resolved_concurrency = _int_from_env("WEB_LOADER_CONCURRENCY")

    results = web_search(
        message,
        num_results=num_results,
        include_page_content=include_page_content,
        page_timeout_s=resolved_page_timeout,
        total_budget_s=resolved_total_budget,
        max_pages=resolved_max_pages,
        concurrency=resolved_concurrency,
    )
    context = format_search_context(message, results)
    return context, results


def _deps() -> ChatUseCaseDependencies:
    return ChatUseCaseDependencies(
        _run_web_search,
        _run_langchain_agent,
        build_chat_model=_build_chat_model,
        resolve_model=resolve_model,
        registry=_REGISTRY,
    )


def chat_once(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
    agent_mode: bool | None = None,
    thinking_mode: bool = True,
    images: list[str] | None = None,
    request_id: str = "chat-once",
) -> str:
    return ChatOnceUseCase(_deps()).execute(
        api_key=api_key,
        message=message,
        history=history,
        model=model,
        enable_search=enable_search,
        agent_mode=agent_mode,
        thinking_mode=thinking_mode,
        images=images,
        request_id=request_id,
    )


def stream_chat(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
    agent_mode: bool | None = None,
    thinking_mode: bool = True,
    images: list[str] | None = None,
    request_id: str = "stream-chat",
):
    stream = StreamChatUseCase(_deps()).execute(
        api_key=api_key,
        message=message,
        history=history,
        model=model,
        enable_search=enable_search,
        agent_mode=agent_mode,
        thinking_mode=thinking_mode,
        images=images,
        request_id=request_id,
    )
    yield from stream.iter_events()


def cancel_chat(request_id: str) -> dict:
    return CancelChatUseCase(_REGISTRY).execute(request_id)


def cancel_active_streams_for_shutdown(timeout_seconds: float) -> dict:
    active_before = _REGISTRY.active_stream_count()
    cancelled = _REGISTRY.cancel_active_streams()
    drained = _REGISTRY.wait_for_no_active_streams(timeout_seconds)
    active_after = _REGISTRY.active_stream_count()
    return {
        "active_streams_before": active_before,
        "cancelled_streams": cancelled,
        "drained": drained,
        "active_streams_after": active_after,
    }

"""Facade module - public API for chat_once / stream_chat.

All heavy logic has been extracted to:
- model_profile: model construction, env helpers, invoke kwargs
- message_builder: message assembly, media normalization, token estimation
- agent_orchestrator: tool-calling agent loop
- event_mapper: SSE event sequence generators
- search_provider: unified search with event emission
"""

from __future__ import annotations

import os

from .config import resolve_model
from .model_registry import supports
from .search_provider import SearchProvider

from .model_profile import proxy_env_guard as _proxy_env_guard
from .model_profile import stream_or_invoke_kwargs as _stream_or_invoke_kwargs
from .provider_router import build_routed_chat_model as _build_chat_model

from .message_builder import (
    build_messages as _build_messages,
    build_user_content as _build_user_content,
    context_usage_payload as _context_usage_payload,
    estimate_tokens_from_messages as _estimate_tokens_from_messages,
    extract_text as _extract_text,
    history_as_text as _history_as_text,
    normalize_image_data_urls as _normalize_image_data_urls,
    normalize_media_data_urls as _normalize_media_data_urls,
)

from .agent_orchestrator import run_agent as _run_langchain_agent

from .event_mapper import stream_agentic, stream_direct


def _supports_thinking(model: str) -> bool:
    return supports(model, "thinking")


def _supports_images(model: str) -> bool:
    return supports(model, "media")


def _is_agentic_model(model: str) -> bool:
    return supports(model, "agent")


def _should_use_agentic_flow(model: str, agent_mode: bool | None) -> bool:
    if agent_mode is False:
        return False
    return _is_agentic_model(model)


def _run_web_search(
    message: str,
    num_results: int = 5,
    include_page_content: bool = True,
    page_timeout_s: float | None = None,
    total_budget_s: float | None = None,
    max_pages: int | None = None,
    concurrency: int | None = None,
):
    """Execute web search and return (context_str, results_list)."""
    from .web_search import format_search_context, web_search

    resolved_page_timeout = page_timeout_s
    if resolved_page_timeout is None:
        raw = os.getenv("WEB_LOADER_TIMEOUT_SECONDS", "").strip()
        if raw:
            try:
                resolved_page_timeout = float(raw)
            except ValueError:
                resolved_page_timeout = None

    resolved_total_budget = total_budget_s
    if resolved_total_budget is None:
        raw = os.getenv("WEB_SEARCH_TOTAL_BUDGET_SECONDS", "").strip()
        if raw:
            try:
                resolved_total_budget = float(raw)
            except ValueError:
                resolved_total_budget = None

    resolved_max_pages = max_pages
    if resolved_max_pages is None:
        raw = os.getenv("WEB_LOADER_MAX_PAGES", "").strip()
        if raw:
            try:
                resolved_max_pages = int(raw)
            except ValueError:
                resolved_max_pages = None

    resolved_concurrency = concurrency
    if resolved_concurrency is None:
        raw = os.getenv("WEB_LOADER_CONCURRENCY", "").strip()
        if raw:
            try:
                resolved_concurrency = int(raw)
            except ValueError:
                resolved_concurrency = None

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


# Public API

def chat_once(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
    agent_mode: bool | None = None,
    thinking_mode: bool = True,
    images: list[str] | None = None,
) -> str:
    chosen_model = resolve_model(model)
    client = _build_chat_model(api_key, chosen_model, thinking_mode=thinking_mode)

    if _should_use_agentic_flow(chosen_model, agent_mode):
        noop_provider = SearchProvider(_run_web_search, lambda evt: None)
        collected_tokens: list[str] = []

        def _collect_token(evt: dict):
            if evt.get("type") == "token":
                collected_tokens.append(evt.get("content", ""))

        with _proxy_env_guard():
            _run_langchain_agent(
                client=client,
                model=chosen_model,
                message=message,
                history=history,
                thinking_mode=thinking_mode,
                search_provider=noop_provider,
                event_emitter=_collect_token,
            )
        return "".join(collected_tokens) or "(No answer produced)"

    initial_search_context = ""
    if enable_search:
        initial_search_context, _ = _run_web_search(message)

    normalized_images = _normalize_media_data_urls(images)
    messages = _build_messages(
        chosen_model, message, history, initial_search_context, normalized_images,
    )

    with _proxy_env_guard():
        response = client.invoke(
            messages, **_stream_or_invoke_kwargs(chosen_model, thinking_mode),
        )

    return _extract_text(getattr(response, "content", ""))


def stream_chat(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
    agent_mode: bool | None = None,
    thinking_mode: bool = True,
    images: list[str] | None = None,
):
    chosen_model = resolve_model(model)
    client = _build_chat_model(api_key, chosen_model, thinking_mode=thinking_mode)
    emit_reasoning = _supports_thinking(chosen_model) and bool(thinking_mode)

    if _should_use_agentic_flow(chosen_model, agent_mode):
        yield from stream_agentic(
            client=client,
            model=chosen_model,
            message=message,
            history=history,
            thinking_mode=thinking_mode,
            emit_reasoning=emit_reasoning,
            run_web_search=_run_web_search,
            run_agent=_run_langchain_agent,
        )
        return

    event_buffer: list[dict] = []
    provider = SearchProvider(_run_web_search, event_buffer.append)

    initial_search_context = ""
    if enable_search:
        initial_search_context, _ = provider.search_with_events(message)
        yield from event_buffer
        event_buffer.clear()

    normalized_images = _normalize_media_data_urls(images)
    messages = _build_messages(
        chosen_model, message, history, initial_search_context, normalized_images,
    )

    yield from stream_direct(
        client=client,
        model=chosen_model,
        messages=messages,
        thinking_mode=thinking_mode,
        emit_reasoning=emit_reasoning,
    )

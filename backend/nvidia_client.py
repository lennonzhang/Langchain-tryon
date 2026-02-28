"""Facade module - public API for chat_once / stream_chat.

All heavy logic has been extracted to:
- model_profile: model construction, env helpers, invoke kwargs
- message_builder: message assembly, media normalization, token estimation
- agent_orchestrator: tool-calling agent loop
- event_mapper: SSE event sequence generators
- search_provider: unified search with event emission
"""

from __future__ import annotations

from .config import resolve_model
from .model_registry import supports
from .search_provider import SearchProvider

from .model_profile import build_chat_model as _build_chat_model
from .model_profile import proxy_env_guard as _proxy_env_guard
from .model_profile import stream_or_invoke_kwargs as _stream_or_invoke_kwargs

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
    if agent_mode is True:
        return _is_agentic_model(model)
    if agent_mode is False:
        return False
    return _is_agentic_model(model)


def _run_web_search(
    message: str,
    num_results: int = 5,
    include_page_content: bool = True,
):
    """Execute web search and return (context_str, results_list)."""
    from .web_search import format_search_context, web_search

    results = web_search(message, num_results=num_results, include_page_content=include_page_content)
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
        agent_events: list[dict] = []
        with _proxy_env_guard():
            return _run_langchain_agent(
                client=client,
                model=chosen_model,
                message=message,
                history=history,
                thinking_mode=thinking_mode,
                search_provider=noop_provider,
                event_collector=agent_events,
            )

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

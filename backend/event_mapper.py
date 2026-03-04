"""SSE event sequence generators for agentic and direct streaming."""

from __future__ import annotations

import queue
import threading
import time

from .message_builder import build_messages, context_usage_payload, extract_text
from .model_profile import proxy_env_guard, stream_or_invoke_kwargs
from .search_provider import SearchProvider

_AGENT_TIMEOUT_S = 600  # 10-minute soft timeout for agent thread


def stream_agentic(
    client,
    model: str,
    message: str,
    history: list,
    thinking_mode: bool,
    emit_reasoning: bool,
    run_web_search=None,
    run_agent=None,
    run_react_agent=None,
):
    """Yield SSE events for the agentic flow using a background thread."""
    if run_web_search is None:
        from .nvidia_client import _run_web_search as run_web_search
    if run_agent is not None and run_react_agent is not None:
        raise ValueError("stream_agentic received both run_agent and run_react_agent")
    if run_agent is None:
        run_agent = run_react_agent
    if run_agent is None:
        from .agent_orchestrator import run_agent

    agent_events: list[dict] = []
    result_queue: queue.Queue = queue.Queue()
    state: dict = {"error": None}

    def _emit_from_agent(event: dict):
        result_queue.put(event)

    search_provider = SearchProvider(run_web_search, _emit_from_agent)

    def _run_agent():
        try:
            with proxy_env_guard():
                run_agent(
                    client=client,
                    model=model,
                    message=message,
                    history=history,
                    thinking_mode=thinking_mode,
                    search_provider=search_provider,
                    event_collector=agent_events,
                    event_emitter=_emit_from_agent,
                    emit_reasoning=emit_reasoning,
                )
        except Exception as exc:  # noqa: BLE001
            state["error"] = exc

    worker = threading.Thread(target=_run_agent, daemon=True)
    worker.start()

    yield {
        "type": "context_usage",
        "usage": context_usage_payload(
            model,
            "agent",
            build_messages(model, message, history, "", []),
        ),
    }

    deadline = time.monotonic() + _AGENT_TIMEOUT_S
    while worker.is_alive() or not result_queue.empty():
        if time.monotonic() > deadline:
            yield {"type": "error", "error": "Agent execution timed out"}
            yield {"type": "done", "finish_reason": "error"}
            return
        try:
            evt = result_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if isinstance(evt, dict) and evt.get("type"):
            yield evt

    if state["error"] is not None:
        yield {"type": "error", "error": str(state["error"])}
        yield {"type": "done", "finish_reason": "error"}
        return

    # Token events have already been streamed by the agent graph.
    yield {"type": "done", "finish_reason": "stop"}


def stream_direct(
    client,
    model: str,
    messages: list[dict],
    thinking_mode: bool,
    emit_reasoning: bool,
):
    """Yield SSE events for the direct (non-agent) streaming flow."""
    stream_kwargs = stream_or_invoke_kwargs(model, thinking_mode)

    has_tokens = False

    with proxy_env_guard():
        yield {
            "type": "context_usage",
            "usage": context_usage_payload(model, "single", messages),
        }

        for chunk in client.stream(messages, **stream_kwargs):
            additional = getattr(chunk, "additional_kwargs", {}) or {}
            reasoning = additional.get("reasoning_content")
            if emit_reasoning and isinstance(reasoning, str) and reasoning:
                yield {"type": "reasoning", "content": reasoning}

            token = extract_text(getattr(chunk, "content", ""))
            if token:
                has_tokens = True
                yield {"type": "token", "content": token}

    if not has_tokens:
        yield {
            "type": "token",
            "content": "(Model returned no visible answer. Try disabling thinking mode.)",
        }
    yield {"type": "done", "finish_reason": "stop"}

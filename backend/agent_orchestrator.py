"""Agent orchestration — delegates to the LangGraph agent graph.

The public ``run_agent`` function builds the graph, assembles the initial
state, and invokes it.  All intermediate and final-answer events are
emitted through the *event_emitter* callback; this function returns
**nothing** (the old ``str`` return has been replaced by ``token`` events).
"""

from __future__ import annotations

import logging

from .agent_graph import AgentState, build_agent_graph
from .application.agent_session_builder import build_agent_initial_messages
from .message_builder import history_as_messages
from .model_registry import get_agent_config
from .tools_registry import build_agent_tools

logger = logging.getLogger(__name__)


def run_agent(
    client,
    model: str,
    message: str,
    history: list,
    thinking_mode: bool,
    search_provider,
    event_collector: list[dict] | None = None,
    event_emitter=None,
    emit_reasoning: bool = False,
    cancel_token=None,
    request_id: str = "",
    provider: str = "",
) -> None:
    """Run the LangGraph agent loop.

    All events — including ``token`` chunks for the final answer — are
    pushed through *event_emitter*.  The caller should **not** expect a
    return value.
    """
    def _emit(event: dict):
        if cancel_token is not None and cancel_token.cancelled:
            return
        if isinstance(event_collector, list):
            event_collector.append(event)
        if callable(event_emitter):
            event_emitter(event)

    # Resolve per-model agent configuration
    agent_cfg = get_agent_config(model)
    enabled_tools = set(agent_cfg.get("tools", []))

    tools = build_agent_tools(
        search_provider=search_provider,
        event_emitter=_emit,
        enabled_tools=enabled_tools or None,
    )

    graph = build_agent_graph(
        client=client,
        model=model,
        tools=tools,
        thinking_mode=thinking_mode,
        emit_reasoning=emit_reasoning,
        event_emitter=_emit,
        request_id=request_id,
        provider=provider,
    )

    # Assemble initial messages
    from .agent_graph import _SYSTEM_PROMPT  # noqa: WPS436

    history_messages = history_as_messages(history)
    initial_messages = build_agent_initial_messages(_SYSTEM_PROMPT, history_messages, message)

    initial_state: AgentState = {
        "messages": initial_messages,
        "step_count": 0,
        "max_steps": agent_cfg.get("max_steps", 6),
        "last_had_tool_calls": False,
        "step_end_emitted": False,
        "enable_planning": agent_cfg.get("enable_planning", False),
        "enable_reflection": agent_cfg.get("enable_reflection", False),
        "pending_user_input": None,
        "interrupted_for_user_input": False,
    }

    if cancel_token is not None and cancel_token.cancelled:
        return
    graph.invoke(initial_state)

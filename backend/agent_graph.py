"""LangGraph-based agent with Plan → Act → Observe → Reflect loop.

Builds a ``StateGraph`` that supports:
- Optional planning phase
- Multi-tool execution with streaming intermediate events
- Optional periodic reflection
- Token-by-token streaming of the final answer
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .message_builder import extract_text, history_as_messages
from .model_profile import stream_or_invoke_kwargs
from .tools_registry import normalize_request_user_input_args

logger = logging.getLogger(__name__)

# ── prompts ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use tools when needed to find information or perform tasks. "
    "Answer in the same language as the user's question. "
    "When you have enough information, respond directly without calling tools. "
    "If key information is missing and the user's answer would change the result, "
    "call request_user_input instead of guessing."
)

_PLAN_PROMPT = (
    "Before acting, briefly plan your approach to answering this question. "
    "List the steps you will take (1-3 short steps). Be concise."
)

_REFLECT_PROMPT = (
    "Review the information gathered so far. "
    "Do you have enough to provide a complete, accurate answer? "
    "If yes, say SUFFICIENT. "
    "If not, briefly state what additional information you need."
)

_FORCE_ANSWER_PROMPT = (
    "You have reached the maximum number of steps. "
    "Based on all information gathered so far, provide your best final answer now."
)


# ── state ───────────────────────────────────────────────────────

def _with_leading_system(messages: list[BaseMessage], instruction: str) -> list[BaseMessage]:
    """Ensure extra instructions live in the first system message only."""
    existing = list(messages)
    if existing and isinstance(existing[0], SystemMessage):
        original = extract_text(getattr(existing[0], "content", "")) or ""
        merged = f"{original}\n\n{instruction}" if original else instruction
        existing[0] = SystemMessage(content=merged)
        return existing
    return [SystemMessage(content=instruction), *existing]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    step_count: int
    max_steps: int
    last_had_tool_calls: bool
    step_end_emitted: bool
    enable_planning: bool
    enable_reflection: bool
    pending_user_input: dict[str, Any] | None
    interrupted_for_user_input: bool


# ── graph builder ───────────────────────────────────────────────

def build_agent_graph(
    *,
    client,
    model: str,
    tools: list,
    thinking_mode: bool,
    emit_reasoning: bool,
    event_emitter: Callable[[dict], None] | None = None,
):
    """Compile and return the LangGraph agent graph.

    Parameters
    ----------
    client:
        The ``ChatNVIDIA`` instance (without tools bound).
    model:
        Model ID string (e.g. ``"qwen/qwen3.5-397b-a17b"``).
    tools:
        List of LangChain ``@tool`` instances.
    thinking_mode:
        Whether thinking/reasoning is enabled.
    emit_reasoning:
        Whether to emit ``reasoning`` events.
    event_emitter:
        Callback to push SSE events (e.g. ``queue.put``).
    """
    invoke_kwargs = stream_or_invoke_kwargs(model, thinking_mode)
    llm_with_tools = client.bind_tools(tools) if tools else client
    tools_by_name = {t.name: t for t in tools}

    def _emit(event: dict):
        if callable(event_emitter):
            event_emitter(event)

    def _extract_reasoning(response):
        additional = getattr(response, "additional_kwargs", {}) or {}
        reasoning = additional.get("reasoning_content")
        if emit_reasoning and isinstance(reasoning, str) and reasoning:
            _emit({"type": "reasoning", "content": reasoning})

    # ── nodes ───────────────────────────────────────────────

    def plan_node(state: AgentState) -> dict:
        if not state.get("enable_planning"):
            return {}

        plan_messages = _with_leading_system(state["messages"], _PLAN_PROMPT)
        response = llm_with_tools.invoke(plan_messages, **invoke_kwargs)
        _extract_reasoning(response)
        plan_text = extract_text(getattr(response, "content", ""))
        if plan_text:
            _emit({"type": "agent_plan", "content": plan_text})
        return {}

    def agent_node(state: AgentState) -> dict:
        step = state["step_count"] + 1
        _emit({
            "type": "agent_step_start",
            "step": step,
            "max_steps": state["max_steps"],
        })

        response = llm_with_tools.invoke(state["messages"], **invoke_kwargs)
        _extract_reasoning(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        has_tool_calls = bool(tool_calls)

        if has_tool_calls:
            step_end_emitted = False
            if step >= state["max_steps"]:
                _emit({"type": "agent_step_end", "step": step})
                step_end_emitted = True
            return {
                "messages": [response],
                "step_count": step,
                "last_had_tool_calls": True,
                "step_end_emitted": step_end_emitted,
            }
        else:
            _emit({"type": "agent_step_end", "step": step})
            # Don't persist the AI message — stream_answer will regenerate
            return {
                "step_count": step,
                "last_had_tool_calls": False,
                "step_end_emitted": True,
            }

    def execute_tools_node(state: AgentState) -> dict:
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", None) or []
        step = state["step_count"]
        new_messages: list[BaseMessage] = []

        user_input_call = next((tc for tc in tool_calls if tc.get("name") == "request_user_input"), None)
        if user_input_call is not None:
            payload = normalize_request_user_input_args(user_input_call.get("args", {}))
            _emit(
                {
                    "type": "user_input_required",
                    "question": payload["question"],
                    "options": payload["options"],
                    "allow_free_text": payload["allow_free_text"],
                    "step": step,
                }
            )
            _emit({"type": "agent_step_end", "step": step})
            return {
                "messages": [
                    ToolMessage(
                        content="User input requested.",
                        tool_call_id=user_input_call["id"],
                    ),
                ],
                "pending_user_input": payload,
                "interrupted_for_user_input": True,
                "step_end_emitted": True,
            }

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("args", {})
            _emit({
                "type": "tool_call",
                "tool": tool_name,
                "input": tool_args,
                "step": step,
            })

            tool_fn = tools_by_name.get(tool_name)
            if tool_fn is None:
                result = f"Unknown tool: {tool_name}"
            else:
                try:
                    result = tool_fn.invoke(tool_args)
                except Exception as exc:  # noqa: BLE001
                    result = f"Tool error: {exc}"

            display = result[:500] if isinstance(result, str) else str(result)[:500]
            _emit({
                "type": "tool_result",
                "tool": tool_name,
                "output": display,
                "step": step,
            })

            new_messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"]),
            )

        _emit({"type": "agent_step_end", "step": step})
        return {
            "messages": new_messages,
            "step_end_emitted": True,
            "pending_user_input": None,
            "interrupted_for_user_input": False,
        }

    def reflect_node(state: AgentState) -> dict:
        if not state.get("enable_reflection"):
            return {}

        step = state["step_count"]
        should_reflect = step > 0 and step % 3 == 0 and step < state["max_steps"]
        if not should_reflect:
            return {}

        reflect_messages = _with_leading_system(state["messages"], _REFLECT_PROMPT)
        response = client.invoke(reflect_messages, **invoke_kwargs)
        _extract_reasoning(response)
        reflect_text = extract_text(getattr(response, "content", ""))
        if reflect_text:
            _emit({"type": "agent_reflect", "content": reflect_text})
        return {}

    def stream_answer_node(state: AgentState) -> dict:
        messages = list(state["messages"])

        # If we're forcing an answer (hit max steps with pending tool calls),
        # remove the last AIMessage (which has unexecuted tool calls) and
        # add a system prompt forcing a final answer.
        if state.get("last_had_tool_calls"):
            if messages and isinstance(messages[-1], AIMessage):
                messages.pop()
            messages = _with_leading_system(messages, _FORCE_ANSWER_PROMPT)

        # Stream final answer token-by-token (no tools bound)
        stream_kwargs = stream_or_invoke_kwargs(model, thinking_mode)
        has_tokens = False
        for chunk in client.stream(messages, **stream_kwargs):
            additional = getattr(chunk, "additional_kwargs", {}) or {}
            reasoning = additional.get("reasoning_content")
            if emit_reasoning and isinstance(reasoning, str) and reasoning:
                _emit({"type": "reasoning", "content": reasoning})

            token = extract_text(getattr(chunk, "content", ""))
            if token:
                has_tokens = True
                _emit({"type": "token", "content": token})

        if not has_tokens:
            _emit({
                "type": "token",
                "content": "(The agent did not produce a final answer. Please try again.)",
            })

        return {"final_streamed": True}

    # ── routing ─────────────────────────────────────────────

    def after_agent(state: AgentState) -> str:
        if state.get("last_had_tool_calls"):
            last_msg = state["messages"][-1] if state.get("messages") else None
            tool_calls = getattr(last_msg, "tool_calls", None) or []
            has_user_input_tool = any(tc.get("name") == "request_user_input" for tc in tool_calls)
            if state["step_count"] >= state["max_steps"] and not has_user_input_tool:
                return "stream_answer"  # Force answer at limit
            return "execute_tools"
        return "stream_answer"

    def after_execute_tools(state: AgentState) -> str:
        if state.get("interrupted_for_user_input"):
            return "done"
        return "reflect"

    # ── graph assembly ──────────────────────────────────────

    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("agent", agent_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("stream_answer", stream_answer_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "agent")
    graph.add_conditional_edges("agent", after_agent, {
        "execute_tools": "execute_tools",
        "stream_answer": "stream_answer",
    })
    graph.add_conditional_edges("execute_tools", after_execute_tools, {
        "done": END,
        "reflect": "reflect",
    })
    graph.add_edge("reflect", "agent")
    graph.add_edge("stream_answer", END)

    return graph.compile()

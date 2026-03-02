"""Tests for the LangGraph-based agent graph."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent_graph import AgentState, build_agent_graph


class FakeLLM:
    """Minimal LLM stub that returns pre-configured responses."""

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self._call_count = 0
        self.invocations = []
        self.stream_invocations = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, **kwargs):
        self.invocations.append(list(messages))
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = self._responses[-1] if self._responses else AIMessage(content="")
        self._call_count += 1
        return resp

    def stream(self, messages, **kwargs):
        self.stream_invocations.append(list(messages))
        # Stream the last response's content as chunks
        if self._responses:
            last = self._responses[-1]
            content = last.content if isinstance(last, AIMessage) else "streamed answer"
        else:
            content = "streamed answer"
        if isinstance(content, str) and content:
            for word in content.split():
                yield SimpleNamespace(
                    content=word + " ",
                    additional_kwargs={},
                )
        else:
            yield SimpleNamespace(content="fallback ", additional_kwargs={})


def _make_ai_msg(content, tool_calls=None):
    """Create a real AIMessage with optional tool_calls."""
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg


def _make_tool_call(name, args, call_id="tc-1"):
    return {"name": name, "args": args, "id": call_id}


def _initial_state(**overrides) -> AgentState:
    defaults: AgentState = {
        "messages": [HumanMessage(content="hello")],
        "step_count": 0,
        "max_steps": 8,
        "last_had_tool_calls": False,
        "step_end_emitted": False,
        "enable_planning": False,
        "enable_reflection": False,
    }
    defaults.update(overrides)
    return defaults


class TestAgentGraphNoTools(unittest.TestCase):
    """Agent immediately gives a final answer (no tool calls)."""

    def test_direct_answer_emits_tokens(self):
        events = []
        ai_response = _make_ai_msg("Direct answer")

        llm = FakeLLM(responses=[ai_response])
        graph = build_agent_graph(
            client=llm,
            model="qwen/qwen3.5-397b-a17b",
            tools=[],
            thinking_mode=True,
            emit_reasoning=False,
            event_emitter=events.append,
        )

        graph.invoke(_initial_state())

        types = [e["type"] for e in events]
        self.assertIn("agent_step_start", types)
        self.assertIn("agent_step_end", types)
        self.assertEqual(types.count("agent_step_start"), types.count("agent_step_end"))
        self.assertIn("token", types)
        token_events = [e for e in events if e["type"] == "token"]
        full_text = "".join(e["content"] for e in token_events)
        self.assertTrue(len(full_text) > 0)

    def test_planning_emits_agent_plan(self):
        events = []
        plan_response = _make_ai_msg("1. Search 2. Analyze")
        answer_response = _make_ai_msg("The answer is 42")

        llm = FakeLLM(responses=[plan_response, answer_response])
        graph = build_agent_graph(
            client=llm,
            model="qwen/qwen3.5-397b-a17b",
            tools=[],
            thinking_mode=True,
            emit_reasoning=False,
            event_emitter=events.append,
        )

        graph.invoke(_initial_state(enable_planning=True))

        types = [e["type"] for e in events]
        self.assertIn("agent_plan", types)
        plan_evt = next(e for e in events if e["type"] == "agent_plan")
        self.assertIn("Search", plan_evt["content"])
        self.assertIsInstance(llm.invocations[0][0], SystemMessage)
        self.assertIn("Before acting, briefly plan your approach", llm.invocations[0][0].content)


class TestAgentGraphWithToolCalls(unittest.TestCase):
    """Agent calls tools and then gives a final answer."""

    def test_tool_call_emits_events(self):
        events = []

        # First response: tool call; second response: final answer
        tool_call_msg = _make_ai_msg(
            "",
            tool_calls=[_make_tool_call("web_search", {"query": "test"})],
        )
        final_msg = _make_ai_msg("Search result summary")

        llm = FakeLLM(responses=[tool_call_msg, final_msg])

        # Create a simple fake tool
        fake_tool = MagicMock()
        fake_tool.name = "web_search"
        fake_tool.invoke.return_value = "search results text"

        graph = build_agent_graph(
            client=llm,
            model="qwen/qwen3.5-397b-a17b",
            tools=[fake_tool],
            thinking_mode=True,
            emit_reasoning=False,
            event_emitter=events.append,
        )

        graph.invoke(_initial_state())

        types = [e["type"] for e in events]
        self.assertIn("tool_call", types)
        self.assertIn("tool_result", types)
        self.assertIn("token", types)
        self.assertEqual(types.count("agent_step_start"), types.count("agent_step_end"))

        tool_call_evt = next(e for e in events if e["type"] == "tool_call")
        self.assertEqual(tool_call_evt["tool"], "web_search")

        tool_result_evt = next(e for e in events if e["type"] == "tool_result")
        self.assertIn("search results", tool_result_evt["output"])

    def test_max_steps_forces_answer(self):
        events = []

        # Agent always wants to call tools
        tool_call_msg = _make_ai_msg(
            "",
            tool_calls=[_make_tool_call("web_search", {"query": "q"}, "tc-loop")],
        )
        llm = FakeLLM(responses=[tool_call_msg])

        fake_tool = MagicMock()
        fake_tool.name = "web_search"
        fake_tool.invoke.return_value = "results"

        graph = build_agent_graph(
            client=llm,
            model="qwen/qwen3.5-397b-a17b",
            tools=[fake_tool],
            thinking_mode=True,
            emit_reasoning=False,
            event_emitter=events.append,
        )

        graph.invoke(_initial_state(max_steps=1))

        types = [e["type"] for e in events]
        # At max_steps, the agent skips tool execution and forces a streamed answer
        self.assertIn("agent_step_start", types)
        self.assertIn("agent_step_end", types)
        self.assertEqual(types.count("agent_step_start"), 1)
        self.assertEqual(types.count("agent_step_end"), 1)
        self.assertIn("token", types)
        # Tool was NOT executed since we were already at the limit
        self.assertNotIn("tool_call", types)
        forced_messages = llm.stream_invocations[0]
        self.assertIsInstance(forced_messages[0], SystemMessage)
        self.assertIn("You have reached the maximum number of steps.", forced_messages[0].content)
        trailing_system = any(isinstance(msg, SystemMessage) for msg in forced_messages[1:])
        self.assertFalse(trailing_system)


class TestAgentGraphReasoning(unittest.TestCase):
    def test_reasoning_emitted_when_enabled(self):
        events = []
        ai_response = AIMessage(
            content="answer",
            additional_kwargs={"reasoning_content": "thinking step"},
        )

        llm = FakeLLM(responses=[ai_response])
        graph = build_agent_graph(
            client=llm,
            model="qwen/qwen3.5-397b-a17b",
            tools=[],
            thinking_mode=True,
            emit_reasoning=True,
            event_emitter=events.append,
        )

        graph.invoke(_initial_state())

        reasoning_events = [e for e in events if e["type"] == "reasoning"]
        self.assertGreaterEqual(len(reasoning_events), 1)
        self.assertIn("thinking step", reasoning_events[0]["content"])

    def test_reasoning_not_emitted_when_disabled(self):
        events = []
        ai_response = AIMessage(
            content="answer",
            additional_kwargs={"reasoning_content": "thinking step"},
        )

        llm = FakeLLM(responses=[ai_response])
        graph = build_agent_graph(
            client=llm,
            model="qwen/qwen3.5-397b-a17b",
            tools=[],
            thinking_mode=True,
            emit_reasoning=False,
            event_emitter=events.append,
        )

        graph.invoke(_initial_state())

        reasoning_events = [e for e in events if e["type"] == "reasoning"]
        self.assertEqual(len(reasoning_events), 0)


if __name__ == "__main__":
    unittest.main()

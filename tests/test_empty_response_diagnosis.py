"""Tests verifying empty-response handling for streaming paths."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.event_mapper import stream_agentic, stream_direct
from backend.nvidia_client import stream_chat


class FakeClient:
    """Minimal client stub for direct-stream tests."""

    def __init__(self, chunks=None):
        self.chunks = chunks or []

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(content="")

    def stream(self, messages, **kwargs):
        for chunk in self.chunks:
            yield chunk


def _collect_events(gen):
    return list(gen)


def _token_events(events):
    return [e for e in events if e.get("type") == "token"]


def _error_events(events):
    return [e for e in events if e.get("type") == "error"]


_AGENTIC_FALLBACK = "(The agent did not produce a final answer. Please try again.)"
_DIRECT_FALLBACK = "(Model returned no visible answer. Try disabling thinking mode.)"


class TestAgenticEmptyAnswer(unittest.TestCase):
    def _run_agentic(self, agent_return_value):
        def fake_agent(**kwargs):
            return agent_return_value

        return _collect_events(
            stream_agentic(
                client=FakeClient(),
                model="qwen/qwen3.5-397b-a17b",
                message="what is the weather",
                history=[],
                thinking_mode=True,
                emit_reasoning=False,
                run_web_search=lambda *a, **k: ("", []),
                run_agent=fake_agent,
            )
        )

    def test_agentic_empty_answer_emits_fallback_token(self):
        events = self._run_agentic("")
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], _AGENTIC_FALLBACK)

    def test_agentic_whitespace_answer_emits_fallback_token(self):
        events = self._run_agentic("  \n  ")
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], _AGENTIC_FALLBACK)

    def test_agentic_normal_answer_produces_token(self):
        events = self._run_agentic("Sunny, around 25C.")
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], "Sunny, around 25C.")


class TestAgenticException(unittest.TestCase):
    def _run_agentic_with_exception(self, exc):
        def fake_agent(**kwargs):
            raise exc

        return _collect_events(
            stream_agentic(
                client=FakeClient(),
                model="z-ai/glm5",
                message="what is the weather",
                history=[],
                thinking_mode=True,
                emit_reasoning=False,
                run_web_search=lambda *a, **k: ("", []),
                run_agent=fake_agent,
            )
        )

    def test_agentic_runtime_error_produces_error_event(self):
        events = self._run_agentic_with_exception(RuntimeError("LLM parse failed"))
        errors = _error_events(events)
        self.assertGreaterEqual(len(errors), 1)
        self.assertIn("LLM parse failed", errors[0]["error"])
        self.assertTrue(any(e.get("finish_reason") == "error" for e in events))

    def test_agentic_timeout_produces_error_event(self):
        events = self._run_agentic_with_exception(TimeoutError("timed out"))
        errors = _error_events(events)
        self.assertGreaterEqual(len(errors), 1)
        self.assertIn("timed out", errors[0]["error"])


class TestDirectReasoningOnly(unittest.TestCase):
    def test_direct_reasoning_only_emits_fallback(self):
        chunks = [
            SimpleNamespace(content="", additional_kwargs={"reasoning_content": "thinking..."}),
            SimpleNamespace(content="", additional_kwargs={"reasoning_content": "still thinking..."}),
        ]
        events = _collect_events(
            stream_direct(
                client=FakeClient(chunks=chunks),
                model="moonshotai/kimi-k2.5",
                messages=[{"role": "user", "content": "weather"}],
                thinking_mode=True,
                emit_reasoning=True,
            )
        )
        tokens = _token_events(events)
        reasoning = [e for e in events if e.get("type") == "reasoning"]
        self.assertEqual(len(reasoning), 2)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], _DIRECT_FALLBACK)

    def test_direct_normal_chunks_has_tokens(self):
        chunks = [
            SimpleNamespace(content="Weather", additional_kwargs={}),
            SimpleNamespace(content=" is sunny", additional_kwargs={}),
        ]
        events = _collect_events(
            stream_direct(
                client=FakeClient(chunks=chunks),
                model="moonshotai/kimi-k2.5",
                messages=[{"role": "user", "content": "weather"}],
                thinking_mode=True,
                emit_reasoning=True,
            )
        )
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0]["content"], "Weather")
        self.assertNotEqual(tokens[0]["content"], _DIRECT_FALLBACK)

    def test_direct_mixed_chunks_partial_tokens(self):
        chunks = [
            SimpleNamespace(content="", additional_kwargs={"reasoning_content": "thinking"}),
            SimpleNamespace(content="answer", additional_kwargs={}),
            SimpleNamespace(content="", additional_kwargs={"reasoning_content": "more"}),
        ]
        events = _collect_events(
            stream_direct(
                client=FakeClient(chunks=chunks),
                model="moonshotai/kimi-k2.5",
                messages=[{"role": "user", "content": "weather"}],
                thinking_mode=True,
                emit_reasoning=True,
            )
        )
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], "answer")

    def test_direct_zero_chunks_emits_fallback(self):
        events = _collect_events(
            stream_direct(
                client=FakeClient(chunks=[]),
                model="moonshotai/kimi-k2.5",
                messages=[{"role": "user", "content": "weather"}],
                thinking_mode=True,
                emit_reasoning=True,
            )
        )
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], _DIRECT_FALLBACK)


class TestAgentOutput(unittest.TestCase):
    def _mock_and_run(self, executor_result):
        mock_executor_instance = MagicMock()
        mock_executor_instance.invoke.return_value = executor_result

        with (
            patch("langchain.agents.AgentExecutor", return_value=mock_executor_instance),
            patch("langchain.agents.create_tool_calling_agent"),
            patch("backend.tools_registry.build_agent_tools", return_value=[]),
        ):
            from backend.agent_orchestrator import run_agent

            return run_agent(
                client=MagicMock(),
                model="qwen/qwen3.5-397b-a17b",
                message="weather",
                history=[],
                thinking_mode=True,
                search_provider=MagicMock(),
            )

    def test_react_agent_output_empty_string(self):
        result = self._mock_and_run({"output": ""})
        self.assertEqual(result, "")

    def test_react_agent_output_missing_key(self):
        result = self._mock_and_run({})
        self.assertEqual(result, "")

    def test_react_agent_output_iteration_limit(self):
        msg = "Agent stopped due to iteration limit or time limit."
        result = self._mock_and_run({"output": msg})
        self.assertEqual(result, msg)

    def test_react_agent_normal_output(self):
        result = self._mock_and_run({"output": "Sunny, around 25C."})
        self.assertEqual(result, "Sunny, around 25C.")

    def test_react_agent_output_only_whitespace(self):
        result = self._mock_and_run({"output": "  \n  "})
        self.assertEqual(result, "")


class TestEndToEndWeatherQuery(unittest.TestCase):
    def test_kimi_direct_path_normal_response(self):
        chunks = [SimpleNamespace(content="Weather is sunny", additional_kwargs={})]
        with (
            patch("backend.nvidia_client.resolve_model", return_value="moonshotai/kimi-k2.5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient(chunks=chunks)),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        tokens = _token_events(events)
        self.assertGreaterEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], "Weather is sunny")

    def test_kimi_direct_path_empty_content_emits_fallback(self):
        chunks = [SimpleNamespace(content="", additional_kwargs={"reasoning_content": "let me think"})]
        with (
            patch("backend.nvidia_client.resolve_model", return_value="moonshotai/kimi-k2.5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient(chunks=chunks)),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1, "Should have fallback token, not zero")
        self.assertEqual(tokens[0]["content"], _DIRECT_FALLBACK)

    def test_qwen_agentic_empty_agent_emits_fallback(self):
        with (
            patch("backend.nvidia_client.resolve_model", return_value="qwen/qwen3.5-397b-a17b"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch("backend.nvidia_client._run_langchain_agent", return_value=""),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1, "Should have fallback token, not zero")
        self.assertEqual(tokens[0]["content"], _AGENTIC_FALLBACK)

    def test_qwen_agentic_normal_agent_answer(self):
        with (
            patch("backend.nvidia_client.resolve_model", return_value="qwen/qwen3.5-397b-a17b"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch("backend.nvidia_client._run_langchain_agent", return_value="Weather is sunny 25C"),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], "Weather is sunny 25C")

    def test_glm5_agentic_empty_agent_emits_fallback(self):
        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch("backend.nvidia_client._run_langchain_agent", return_value=""),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], _AGENTIC_FALLBACK)


if __name__ == "__main__":
    unittest.main()

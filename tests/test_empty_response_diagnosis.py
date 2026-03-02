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
    def _run_agentic(self, token_content=None):
        """Run the agentic flow with a fake agent that emits events."""
        def fake_agent(**kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter) and token_content:
                emitter({"type": "token", "content": token_content})

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

    def test_agentic_empty_answer_emits_done(self):
        events = self._run_agentic(None)
        tokens = _token_events(events)
        self.assertEqual(len(tokens), 0)
        self.assertTrue(any(e.get("type") == "done" for e in events))

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
    """Test the LangGraph-based run_agent via event emission."""

    def _run_and_collect(self, graph_side_effect=None):
        events: list[dict] = []

        def _emitter(evt):
            events.append(evt)

        mock_graph = MagicMock()
        if graph_side_effect:
            mock_graph.invoke.side_effect = graph_side_effect
        else:
            mock_graph.invoke.return_value = {}

        with (
            patch("backend.agent_orchestrator.build_agent_graph", return_value=mock_graph),
            patch("backend.agent_orchestrator.build_agent_tools", return_value=[]),
        ):
            from backend.agent_orchestrator import run_agent

            run_agent(
                client=MagicMock(),
                model="qwen/qwen3.5-397b-a17b",
                message="weather",
                history=[],
                thinking_mode=True,
                search_provider=MagicMock(),
                event_emitter=_emitter,
            )
        return events

    def test_agent_graph_invoked(self):
        events = self._run_and_collect()
        # Graph was called; no token events since the mock graph does nothing
        self.assertIsInstance(events, list)

    def test_agent_exception_propagates(self):
        with self.assertRaises(RuntimeError):
            self._run_and_collect(
                graph_side_effect=RuntimeError("LLM parse failed"),
            )


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

    def test_qwen_agentic_empty_agent_emits_done(self):
        def _fake_agent(*args, **kwargs):
            pass  # emit no tokens

        with (
            patch("backend.nvidia_client.resolve_model", return_value="qwen/qwen3.5-397b-a17b"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch("backend.nvidia_client._run_langchain_agent", side_effect=_fake_agent),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        self.assertTrue(any(e.get("type") == "done" for e in events))

    def test_qwen_agentic_normal_agent_answer(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "token", "content": "Weather is sunny 25C"})

        with (
            patch("backend.nvidia_client.resolve_model", return_value="qwen/qwen3.5-397b-a17b"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch("backend.nvidia_client._run_langchain_agent", side_effect=_fake_agent),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        tokens = _token_events(events)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["content"], "Weather is sunny 25C")

    def test_glm5_agentic_empty_agent_emits_done(self):
        def _fake_agent(*args, **kwargs):
            pass  # emit no tokens

        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch("backend.nvidia_client._run_langchain_agent", side_effect=_fake_agent),
        ):
            events = _collect_events(stream_chat("key", "weather", [], thinking_mode=True))

        self.assertTrue(any(e.get("type") == "done" for e in events))


if __name__ == "__main__":
    unittest.main()

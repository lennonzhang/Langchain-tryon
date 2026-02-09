import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.nvidia_client import _build_messages, chat_once, stream_chat


class FakeClient:
    def __init__(self, invoke_content="", chunks=None):
        self.invoke_content = invoke_content
        self.chunks = chunks or []
        self.invoked_messages = None
        self.stream_messages = None
        self.stream_kwargs = None

    def invoke(self, messages):
        self.invoked_messages = messages
        return SimpleNamespace(content=self.invoke_content)

    def stream(self, messages, **kwargs):
        self.stream_messages = messages
        self.stream_kwargs = kwargs
        for chunk in self.chunks:
            yield chunk


class TestNvidiaClient(unittest.TestCase):
    def test_build_messages_includes_search_context_first(self):
        messages = _build_messages(
            "user question",
            [{"role": "assistant", "content": "history"}],
            search_context="search ctx",
        )
        self.assertEqual(messages[0], {"role": "system", "content": "search ctx"})
        self.assertEqual(messages[-1], {"role": "user", "content": "user question"})

    def test_chat_once_injects_search_context_when_enabled(self):
        fake_client = FakeClient(invoke_content="final answer")
        with (
            patch("backend.nvidia_client.resolve_model", return_value="moonshotai/kimi-k2.5"),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch(
                "backend.nvidia_client._run_web_search",
                return_value=("search system context", [{"title": "r1"}]),
            ) as run_search,
        ):
            answer = chat_once(
                "api-key",
                "question",
                [{"role": "user", "content": "old"}],
                enable_search=True,
            )

        self.assertEqual(answer, "final answer")
        run_search.assert_called_once_with("question")
        self.assertEqual(
            fake_client.invoked_messages[0],
            {"role": "system", "content": "search system context"},
        )

    def test_stream_chat_emits_search_events_and_stream_content(self):
        chunks = [
            SimpleNamespace(
                content="token-1",
                additional_kwargs={"reasoning_content": "think-1"},
            ),
            SimpleNamespace(content="token-2", additional_kwargs={}),
        ]
        fake_client = FakeClient(chunks=chunks)

        with (
            patch("backend.nvidia_client.resolve_model", return_value="moonshotai/kimi-k2.5"),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch(
                "backend.nvidia_client._run_web_search",
                return_value=("search system context", [{"title": "r1"}]),
            ),
        ):
            events = list(
                stream_chat(
                    "api-key",
                    "question",
                    [],
                    enable_search=True,
                )
            )

        self.assertEqual(events[0]["type"], "search_start")
        self.assertEqual(events[1]["type"], "search_done")
        self.assertIn({"type": "reasoning", "content": "think-1"}, events)
        self.assertIn({"type": "token", "content": "token-1"}, events)
        self.assertIn({"type": "token", "content": "token-2"}, events)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(
            fake_client.stream_kwargs,
            {"chat_template_kwargs": {"thinking": True}},
        )

    def test_stream_chat_search_error_does_not_block_answer(self):
        chunks = [SimpleNamespace(content="token-ok", additional_kwargs={})]
        fake_client = FakeClient(chunks=chunks)

        with (
            patch("backend.nvidia_client.resolve_model", return_value="moonshotai/kimi-k2.5"),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch("backend.nvidia_client._run_web_search", side_effect=RuntimeError("search failed")),
        ):
            events = list(
                stream_chat(
                    "api-key",
                    "question",
                    [],
                    enable_search=True,
                )
            )

        self.assertEqual(events[0]["type"], "search_start")
        self.assertEqual(events[1]["type"], "search_error")
        self.assertIn({"type": "token", "content": "token-ok"}, events)
        self.assertEqual(events[-1]["type"], "done")


if __name__ == "__main__":
    unittest.main()

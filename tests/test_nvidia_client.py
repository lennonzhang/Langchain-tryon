import unittest
from types import SimpleNamespace
from unittest.mock import patch
import types
import sys

from backend.nvidia_client import (
    _build_chat_model,
    _build_messages,
    _normalize_media_data_urls,
    chat_once,
    stream_chat,
)


class FakeClient:
    def __init__(self, invoke_content="", chunks=None):
        self.invoke_content = invoke_content
        self.chunks = chunks or []
        self.invoked_messages = None
        self.invoke_kwargs = None
        self.stream_messages = None
        self.stream_kwargs = None

    def invoke(self, messages, **kwargs):
        self.invoked_messages = messages
        self.invoke_kwargs = kwargs
        return SimpleNamespace(content=self.invoke_content)

    def stream(self, messages, **kwargs):
        self.stream_messages = messages
        self.stream_kwargs = kwargs
        for chunk in self.chunks:
            yield chunk


class TestNvidiaClient(unittest.TestCase):
    def test_build_chat_model_zai_thinking_on(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}):
            _build_chat_model("api-key", "z-ai/glm4.7", thinking_mode=True)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"], True)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["clear_thinking"], False)

    def test_build_chat_model_zai_thinking_off(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}):
            _build_chat_model("api-key", "z-ai/glm4.7", thinking_mode=False)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"], False)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["clear_thinking"], True)

    def test_build_messages_includes_search_context_first(self):
        messages = _build_messages(
            "moonshotai/kimi-k2.5",
            "user question",
            [{"role": "assistant", "content": "history"}],
            search_context="search ctx",
        )
        self.assertEqual(messages[0], {"role": "system", "content": "search ctx"})
        self.assertEqual(messages[-1]["role"], "user")

    def test_build_messages_kimi_supports_images(self):
        messages = _build_messages(
            "moonshotai/kimi-k2.5",
            "describe image",
            [],
            images=["data:image/png;base64,abcd"],
        )
        user_content = messages[-1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")

    def test_build_messages_kimi_supports_image_and_video(self):
        messages = _build_messages(
            "moonshotai/kimi-k2.5",
            "describe media",
            [],
            images=[
                "data:image/png;base64,abcd",
                "data:video/mp4;base64,efgh",
            ],
        )
        user_content = messages[-1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertEqual(user_content[2]["type"], "video_url")

    def test_build_messages_zai_ignores_images(self):
        messages = _build_messages(
            "z-ai/glm4.7",
            "describe image",
            [],
            images=["data:image/png;base64,abcd"],
        )
        self.assertIsInstance(messages[-1]["content"], str)

    def test_normalize_media_filters_invalid(self):
        normalized = _normalize_media_data_urls(
            [
                "data:image/png;base64,abcd",
                "data:video/mp4;base64,efgh",
                "http://bad",
                123,
                "data:image/jpeg;base64,xyz",
            ]
        )
        self.assertEqual(
            normalized,
            [
                "data:image/png;base64,abcd",
                "data:video/mp4;base64,efgh",
                "data:image/jpeg;base64,xyz",
            ],
        )

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
                thinking_mode=False,
                images=["data:image/png;base64,abcd"],
            )

        self.assertEqual(answer, "final answer")
        run_search.assert_called_once_with("question")
        self.assertEqual(
            fake_client.invoked_messages[0],
            {"role": "system", "content": "search system context"},
        )
        self.assertEqual(fake_client.invoke_kwargs["max_completion_tokens"], 16384)
        self.assertEqual(fake_client.invoke_kwargs["chat_template_kwargs"], {"thinking": False})

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
                    thinking_mode=True,
                    images=["data:image/png;base64,abcd"],
                )
            )

        self.assertEqual(events[0]["type"], "search_start")
        self.assertEqual(events[1]["type"], "search_done")
        self.assertTrue(any(evt.get("type") == "context_usage" for evt in events))
        self.assertIn({"type": "reasoning", "content": "think-1"}, events)
        self.assertIn({"type": "token", "content": "token-1"}, events)
        self.assertIn({"type": "token", "content": "token-2"}, events)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(
            fake_client.stream_kwargs,
            {
                "max_completion_tokens": 16384,
                "chat_template_kwargs": {"thinking": True},
            },
        )

    def test_stream_chat_zai_thinking_off_hides_reasoning(self):
        fake_client = FakeClient(
            chunks=[
                SimpleNamespace(
                    content="ok",
                    additional_kwargs={"reasoning_content": "hidden-think"},
                )
            ]
        )

        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm4.7"),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client) as build_model_mock,
        ):
            events = list(
                stream_chat(
                    "api-key",
                    "question",
                    [],
                    enable_search=False,
                    thinking_mode=False,
                )
            )

        build_model_mock.assert_called_once_with(
            "api-key",
            "z-ai/glm4.7",
            thinking_mode=False,
        )
        self.assertIn({"type": "token", "content": "ok"}, events)
        self.assertFalse(any(evt.get("type") == "reasoning" for evt in events))
        self.assertEqual(fake_client.stream_kwargs, {"max_completion_tokens": 16384})

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

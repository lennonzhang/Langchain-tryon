import unittest
from types import SimpleNamespace
from unittest.mock import patch
import types
import sys
import time

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
            _build_chat_model("api-key", "z-ai/glm5", thinking_mode=True)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"], True)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["clear_thinking"], False)

    def test_build_chat_model_zai_thinking_off(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}):
            _build_chat_model("api-key", "z-ai/glm5", thinking_mode=False)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"], False)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["clear_thinking"], True)

    def test_build_chat_model_qwen_defaults(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}):
            _build_chat_model("api-key", "qwen/qwen3.5-397b-a17b", thinking_mode=True)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["temperature"], 0.6)
        self.assertEqual(kwargs["top_p"], 0.95)

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
            "z-ai/glm5",
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

    def test_chat_once_kimi_search_keeps_non_agentic_injection(self):
        fake_client = FakeClient(invoke_content="ok")
        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="moonshotai/kimi-k2.5",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch(
                "backend.nvidia_client._run_web_search",
                return_value=("search system context", [{"title": "r1"}]),
            ) as run_search,
        ):
            answer = chat_once(
                "api-key",
                "question",
                [],
                model="moonshotai/kimi-k2.5",
                enable_search=True,
            )

        self.assertEqual(answer, "ok")
        run_search.assert_called_once_with("question")
        self.assertEqual(
            fake_client.invoked_messages[0],
            {"role": "system", "content": "search system context"},
        )

    def test_chat_once_search_enabled_runs_initial_search_for_all_models(self):
        models = [
            "moonshotai/kimi-k2.5",
            "qwen/qwen3.5-397b-a17b",
            "z-ai/glm5",
        ]

        for model in models:
            with self.subTest(model=model):
                fake_client = FakeClient(invoke_content="Thought: done\nAction: final\nAction Input: ok")
                with (
                    patch("backend.nvidia_client.resolve_model", return_value=model),
                    patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
                    patch(
                        "backend.nvidia_client._run_web_search",
                        return_value=("search system context", [{"title": "r1"}]),
                    ) as run_search,
                ):
                    chat_once(
                        "api-key",
                        "question",
                        [],
                        model=model,
                        enable_search=True,
                    )

                run_search.assert_any_call("question")

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
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
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
            "z-ai/glm5",
            thinking_mode=False,
        )
        self.assertIn({"type": "token", "content": "ok"}, events)
        self.assertFalse(any(evt.get("type") == "reasoning" for evt in events))
        self.assertEqual(fake_client.stream_kwargs, {"max_completion_tokens": 16384})

    def test_stream_chat_qwen_thinking_on_emits_reasoning(self):
        fake_client = FakeClient(
            chunks=[
                SimpleNamespace(
                    content="ok",
                    additional_kwargs={"reasoning_content": "think-qwen"},
                )
            ]
        )

        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="qwen/qwen3.5-397b-a17b",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
        ):
            events = list(
                stream_chat(
                    "api-key",
                    "question",
                    [],
                    enable_search=False,
                    thinking_mode=True,
                )
            )

        self.assertIn({"type": "reasoning", "content": "think-qwen"}, events)
        self.assertIn({"type": "token", "content": "ok"}, events)
        self.assertEqual(
            fake_client.stream_kwargs,
            {
                "max_completion_tokens": 16384,
                "chat_template_kwargs": {"enable_thinking": True},
            },
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

    def test_chat_once_qwen_agentic_react_without_manual_search_toggle(self):
        fake_client = FakeClient()
        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="qwen/qwen3.5-397b-a17b",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch(
                "backend.nvidia_client._run_langchain_react_agent",
                return_value="Final summary",
            ) as run_agent,
        ):
            answer = chat_once(
                "api-key",
                "question",
                [],
                enable_search=False,
                agent_mode=True,
                thinking_mode=True,
            )

        self.assertEqual(answer, "Final summary")
        run_agent.assert_called_once()

    def test_stream_chat_zai_agentic_react_emits_search_and_final_token(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "search_start", "query": "langchain react pattern"})
                emitter({"type": "search_done", "results": [{"title": "r1"}]})
                emitter({"type": "reasoning", "content": "agent thought"})
            return "final agent answer"

        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch(
                "backend.nvidia_client._run_langchain_react_agent",
                side_effect=_fake_agent,
            ) as run_agent,
        ):
            events = list(
                stream_chat(
                    "api-key",
                    "question",
                    [],
                    enable_search=False,
                    agent_mode=True,
                    thinking_mode=True,
                )
            )

        run_agent.assert_called_once()
        self.assertTrue(run_agent.call_args.kwargs.get("emit_reasoning"))
        self.assertTrue(any(evt.get("type") == "context_usage" for evt in events))
        self.assertIn({"type": "search_start", "query": "langchain react pattern"}, events)
        self.assertTrue(any(evt.get("type") == "search_done" for evt in events))
        self.assertIn({"type": "reasoning", "content": "agent thought"}, events)
        self.assertIn({"type": "token", "content": "final agent answer"}, events)
        self.assertEqual(events[-1]["type"], "done")

    def test_stream_chat_agent_mode_emits_events_before_agent_finishes(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "search_start", "query": "early-query"})
            time.sleep(0.3)
            return "final"

        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch(
                "backend.nvidia_client._run_langchain_react_agent",
                side_effect=_fake_agent,
            ),
        ):
            events = stream_chat(
                "api-key",
                "question",
                [],
                enable_search=False,
                agent_mode=True,
                thinking_mode=True,
            )
            first = next(events)
            start = time.monotonic()
            second = next(events)
            elapsed = time.monotonic() - start

        self.assertEqual(first["type"], "context_usage")
        self.assertEqual(second, {"type": "search_start", "query": "early-query"})
        self.assertLess(elapsed, 0.2)


if __name__ == "__main__":
    unittest.main()

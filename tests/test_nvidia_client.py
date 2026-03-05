import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch
import types
import sys
import time

from backend.nvidia_client import (
    _build_chat_model,
    _build_messages,
    _normalize_media_data_urls,
    _run_web_search,
    _should_use_agentic_flow,
    chat_once,
    stream_chat,
)
from backend.model_profile import output_tokens


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
    def test_run_web_search_forwards_explicit_controls(self):
        with (
            patch("backend.web_search.web_search", return_value=[{"title": "T"}]) as web_search_mock,
            patch("backend.web_search.format_search_context", return_value="ctx"),
        ):
            context, results = _run_web_search(
                "question",
                num_results=7,
                include_page_content=True,
                page_timeout_s=1.5,
                total_budget_s=3.5,
                max_pages=2,
                concurrency=4,
            )

        self.assertEqual(context, "ctx")
        self.assertEqual(results, [{"title": "T"}])
        web_search_mock.assert_called_once_with(
            "question",
            num_results=7,
            include_page_content=True,
            page_timeout_s=1.5,
            total_budget_s=3.5,
            max_pages=2,
            concurrency=4,
        )

    def test_run_web_search_reads_controls_from_env(self):
        with (
            patch.dict(
                os.environ,
                {
                    "WEB_LOADER_TIMEOUT_SECONDS": "2.5",
                    "WEB_SEARCH_TOTAL_BUDGET_SECONDS": "5.5",
                    "WEB_LOADER_MAX_PAGES": "4",
                    "WEB_LOADER_CONCURRENCY": "6",
                },
                clear=False,
            ),
            patch("backend.web_search.web_search", return_value=[]) as web_search_mock,
            patch("backend.web_search.format_search_context", return_value=""),
        ):
            _run_web_search("question")

        web_search_mock.assert_called_once_with(
            "question",
            num_results=5,
            include_page_content=True,
            page_timeout_s=2.5,
            total_budget_s=5.5,
            max_pages=4,
            concurrency=6,
        )

    def test_build_chat_model_zai_thinking_on(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with (
            patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "nv-key"}, clear=False),
        ):
            _build_chat_model("api-key", "z-ai/glm5", thinking_mode=True)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"], True)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["clear_thinking"], False)

    def test_build_chat_model_zai_thinking_off(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with (
            patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "nv-key"}, clear=False),
        ):
            _build_chat_model("api-key", "z-ai/glm5", thinking_mode=False)

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"], False)
        self.assertEqual(kwargs["extra_body"]["chat_template_kwargs"]["clear_thinking"], True)

    def test_build_chat_model_qwen_defaults(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = unittest.mock.Mock()
        fake_module.ChatNVIDIA = chat_cls
        with (
            patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "nv-key"}, clear=False),
        ):
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

    def test_build_messages_merges_history_system_into_first_system(self):
        messages = _build_messages(
            "qwen/qwen3.5-397b-a17b",
            "latest question",
            [
                {"role": "user", "content": "u1"},
                {"role": "system", "content": "policy from history"},
                {"role": "assistant", "content": "a1"},
            ],
            search_context="search ctx",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("search ctx", messages[0]["content"])
        self.assertIn("policy from history", messages[0]["content"])
        trailing_system = any(m.get("role") == "system" for m in messages[1:])
        self.assertFalse(trailing_system)

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
        self.assertEqual(fake_client.invoke_kwargs["max_completion_tokens"], output_tokens())
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

    def test_chat_once_search_enabled_runs_initial_search_for_all_models_when_agent_disabled(self):
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
                        agent_mode=False,
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
        final_usage_events = [
            evt for evt in events
            if evt.get("type") == "context_usage" and evt.get("usage", {}).get("phase") == "final"
        ]
        self.assertEqual(len(final_usage_events), 1)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(
            fake_client.stream_kwargs,
            {
                "max_completion_tokens": output_tokens(),
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
                    agent_mode=False,
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
        self.assertEqual(fake_client.stream_kwargs, {"max_completion_tokens": output_tokens()})

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
                    agent_mode=False,
                    thinking_mode=True,
                )
            )

        self.assertIn({"type": "reasoning", "content": "think-qwen"}, events)
        self.assertIn({"type": "token", "content": "ok"}, events)
        self.assertEqual(
            fake_client.stream_kwargs,
            {
                "max_completion_tokens": output_tokens(),
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
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "token", "content": "Final summary"})

        fake_client = FakeClient()
        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="qwen/qwen3.5-397b-a17b",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch(
                "backend.nvidia_client._run_langchain_agent",
                side_effect=_fake_agent,
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

    def test_chat_once_qwen_agentic_react_auto_enabled_by_default(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "token", "content": "Final summary"})

        fake_client = FakeClient()
        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="qwen/qwen3.5-397b-a17b",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch(
                "backend.nvidia_client._run_langchain_agent",
                side_effect=_fake_agent,
            ) as run_agent,
        ):
            answer = chat_once(
                "api-key",
                "question",
                [],
                enable_search=False,
                thinking_mode=True,
            )

        self.assertEqual(answer, "Final summary")
        run_agent.assert_called_once()

    def test_chat_once_kimi_auto_agent_disabled_by_default(self):
        fake_client = FakeClient(invoke_content="normal")
        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="moonshotai/kimi-k2.5",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=fake_client),
            patch("backend.nvidia_client._run_langchain_agent") as run_agent,
        ):
            answer = chat_once(
                "api-key",
                "question",
                [],
                enable_search=False,
                thinking_mode=True,
            )

        self.assertEqual(answer, "normal")
        run_agent.assert_not_called()

    def test_should_use_agentic_flow_defaults_and_overrides(self):
        self.assertTrue(_should_use_agentic_flow("qwen/qwen3.5-397b-a17b", None))
        self.assertTrue(_should_use_agentic_flow("z-ai/glm5", None))
        self.assertFalse(_should_use_agentic_flow("moonshotai/kimi-k2.5", None))
        self.assertTrue(_should_use_agentic_flow("anthropic/claude-sonnet-4-6", None))
        self.assertTrue(_should_use_agentic_flow("openai/gpt-5.3-codex", None))
        self.assertTrue(_should_use_agentic_flow("google/gemini-3-pro-preview", None))
        self.assertFalse(_should_use_agentic_flow("z-ai/glm5", False))
        self.assertFalse(_should_use_agentic_flow("moonshotai/kimi-k2.5", True))
        self.assertTrue(_should_use_agentic_flow("z-ai/glm5", True))

    def test_stream_chat_qwen_agentic_react_auto_enabled_by_default(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "token", "content": "final"})

        with (
            patch(
                "backend.nvidia_client.resolve_model",
                return_value="qwen/qwen3.5-397b-a17b",
            ),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch(
                "backend.nvidia_client._run_langchain_agent",
                side_effect=_fake_agent,
            ) as run_agent,
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

        run_agent.assert_called_once()
        self.assertIn({"type": "token", "content": "final"}, events)

    def test_stream_chat_zai_agentic_react_emits_search_and_final_token(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "search_start", "query": "langchain react pattern"})
                emitter({"type": "search_done", "results": [{"title": "r1"}]})
                emitter({"type": "reasoning", "content": "agent thought"})
                emitter({"type": "token", "content": "final agent answer"})

        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch(
                "backend.nvidia_client._run_langchain_agent",
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
        final_usage_events = [
            evt for evt in events
            if evt.get("type") == "context_usage" and evt.get("usage", {}).get("phase") == "final"
        ]
        self.assertEqual(len(final_usage_events), 1)
        self.assertEqual(events[-1]["type"], "done")

    def test_stream_chat_agent_mode_emits_events_before_agent_finishes(self):
        def _fake_agent(*args, **kwargs):
            emitter = kwargs.get("event_emitter")
            if callable(emitter):
                emitter({"type": "search_start", "query": "early-query"})
            time.sleep(0.3)
            emitter({"type": "token", "content": "final"})

        with (
            patch("backend.nvidia_client.resolve_model", return_value="z-ai/glm5"),
            patch("backend.nvidia_client._build_chat_model", return_value=FakeClient()),
            patch(
                "backend.nvidia_client._run_langchain_agent",
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

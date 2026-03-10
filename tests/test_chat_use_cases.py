import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.application.chat_use_cases import ChatOnceUseCase, ChatUseCaseDependencies, StreamChatUseCase
from backend.application.search_service import SearchService
from backend.domain.execution import CancellationRegistry


class _FakeClient:
    def invoke(self, messages, **kwargs):
        return SimpleNamespace(content="final answer")


class TestChatUseCases(unittest.TestCase):
    def test_chat_once_uses_search_service_for_non_agent_search(self):
        search_service = Mock(spec=SearchService)
        search_service.search_with_events.return_value = ("search context", [{"title": "r1"}])

        deps = ChatUseCaseDependencies(
            run_web_search=Mock(),
            run_agent=Mock(),
            build_chat_model=Mock(return_value=_FakeClient()),
            resolve_model=Mock(return_value="moonshotai/kimi-k2.5"),
            search_service=search_service,
        )

        answer = ChatOnceUseCase(deps).execute(
            api_key="api-key",
            message="question",
            history=[],
            model="moonshotai/kimi-k2.5",
            enable_search=True,
            agent_mode=False,
            thinking_mode=False,
            images=[],
            request_id="rid-1",
        )

        self.assertEqual(answer, "final answer")
        search_service.search_with_events.assert_called_once()
        call = search_service.search_with_events.call_args
        self.assertEqual(call.args[0], "question")
        self.assertTrue(call.kwargs["cancel_token"] is not None)

    def test_stream_chat_emits_error_and_done_when_build_chat_model_fails(self):
        registry = CancellationRegistry()
        deps = ChatUseCaseDependencies(
            run_web_search=Mock(),
            run_agent=Mock(),
            build_chat_model=Mock(side_effect=RuntimeError("client init failed")),
            resolve_model=Mock(return_value="moonshotai/kimi-k2.5"),
            registry=registry,
        )

        stream = StreamChatUseCase(deps).execute(
            api_key="api-key",
            message="question",
            history=[],
            model="moonshotai/kimi-k2.5",
            enable_search=False,
            agent_mode=False,
            thinking_mode=False,
            images=[],
            request_id="rid-stream-init-fail",
        )

        events = list(stream.iter_events())

        self.assertEqual(events[0]["type"], "error")
        self.assertIn("client init failed", events[0]["error"])
        self.assertEqual(events[1], {"type": "done", "finish_reason": "error"})
        self.assertEqual(registry.active_stream_count(), 0)

    def test_chat_once_returns_clarification_question_when_agent_interrupts(self):
        def _run_agent(event_emitter=None, **kwargs):
            _ = kwargs
            event_emitter(
                {
                    "type": "user_input_required",
                    "question": "Which cloud provider should I target?",
                    "options": [{"label": "aws"}],
                    "allow_free_text": True,
                    "step": 1,
                }
            )

        deps = ChatUseCaseDependencies(
            run_web_search=Mock(),
            run_agent=_run_agent,
            build_chat_model=Mock(return_value=_FakeClient()),
            resolve_model=Mock(return_value="openai/gpt-5.3-codex"),
        )

        answer = ChatOnceUseCase(deps).execute(
            api_key="api-key",
            message="question",
            history=[],
            model="openai/gpt-5.3-codex",
            enable_search=False,
            agent_mode=True,
            thinking_mode=False,
            images=[],
            request_id="rid-agent-interrupt",
        )

        self.assertEqual(answer, "Which cloud provider should I target?")


if __name__ == "__main__":
    unittest.main()

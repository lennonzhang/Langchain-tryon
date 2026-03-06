import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.application.chat_use_cases import ChatOnceUseCase, ChatUseCaseDependencies
from backend.application.search_service import SearchService


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


if __name__ == "__main__":
    unittest.main()

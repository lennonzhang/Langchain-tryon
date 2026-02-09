import json
import unittest
from unittest.mock import patch

from backend.chat_handlers import handle_chat_once, handle_chat_stream


class TestChatHandlers(unittest.TestCase):
    def test_handle_chat_once_passes_web_search_flag(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={
                    "message": "hello",
                    "history": [],
                    "model": "moonshotai/kimi-k2.5",
                    "web_search": True,
                },
            ),
            patch("backend.chat_handlers.chat_once", return_value="ok") as chat_once_mock,
            patch("backend.chat_handlers.send_json") as send_json_mock,
        ):
            handle_chat_once(handler, "api-key")

        chat_once_mock.assert_called_once_with(
            "api-key",
            "hello",
            [],
            "moonshotai/kimi-k2.5",
            enable_search=True,
        )
        send_json_mock.assert_called_once_with(handler, 200, {"answer": "ok"})

    def test_handle_chat_stream_passes_web_search_flag(self):
        events = [{"type": "search_start"}, {"type": "done"}]
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={
                    "message": "hello",
                    "history": [],
                    "model": "moonshotai/kimi-k2.5",
                    "web_search": True,
                },
            ),
            patch("backend.chat_handlers.init_sse") as init_sse_mock,
            patch("backend.chat_handlers.stream_chat", return_value=iter(events)) as stream_chat_mock,
            patch("backend.chat_handlers.send_sse_event") as send_sse_mock,
        ):
            handle_chat_stream(handler, "api-key")

        init_sse_mock.assert_called_once_with(handler)
        stream_chat_mock.assert_called_once_with(
            "api-key",
            "hello",
            [],
            "moonshotai/kimi-k2.5",
            enable_search=True,
        )
        self.assertEqual(send_sse_mock.call_count, 2)

    def test_handle_chat_once_invalid_json(self):
        handler = object()
        with (
            patch("backend.chat_handlers.read_json_body", side_effect=json.JSONDecodeError("x", "y", 0)),
            patch("backend.chat_handlers.send_json") as send_json_mock,
        ):
            handle_chat_once(handler, "api-key")

        send_json_mock.assert_called_once_with(handler, 400, {"error": "Invalid JSON body"})


if __name__ == "__main__":
    unittest.main()

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
            agent_mode=None,
            thinking_mode=True,
            images=[],
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
            agent_mode=None,
            thinking_mode=True,
            images=[],
        )
        self.assertEqual(send_sse_mock.call_count, 2)

    def test_handle_chat_stream_passes_thinking_and_images(self):
        events = [{"type": "done"}]
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={
                    "message": "hello",
                    "history": [],
                    "model": "moonshotai/kimi-k2.5",
                    "web_search": False,
                    "thinking_mode": False,
                    "images": ["data:image/png;base64,abcd"],
                },
            ),
            patch("backend.chat_handlers.init_sse"),
            patch("backend.chat_handlers.stream_chat", return_value=iter(events)) as stream_chat_mock,
            patch("backend.chat_handlers.send_sse_event"),
        ):
            handle_chat_stream(handler, "api-key")

        stream_chat_mock.assert_called_once_with(
            "api-key",
            "hello",
            [],
            "moonshotai/kimi-k2.5",
            enable_search=False,
            agent_mode=None,
            thinking_mode=False,
            images=["data:image/png;base64,abcd"],
        )

    def test_handle_chat_once_passes_explicit_agent_mode_true(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={
                    "message": "hello",
                    "history": [],
                    "model": "z-ai/glm5",
                    "agent_mode": True,
                },
            ),
            patch("backend.chat_handlers.chat_once", return_value="ok") as chat_once_mock,
            patch("backend.chat_handlers.send_json"),
        ):
            handle_chat_once(handler, "api-key")

        self.assertTrue(chat_once_mock.call_args.kwargs["agent_mode"])

    def test_handle_chat_stream_passes_explicit_agent_mode_false(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={
                    "message": "hello",
                    "history": [],
                    "model": "qwen/qwen3.5-397b-a17b",
                    "agent_mode": False,
                },
            ),
            patch("backend.chat_handlers.init_sse"),
            patch("backend.chat_handlers.stream_chat", return_value=iter([{"type": "done"}])) as stream_chat_mock,
            patch("backend.chat_handlers.send_sse_event"),
        ):
            handle_chat_stream(handler, "api-key")

        self.assertFalse(stream_chat_mock.call_args.kwargs["agent_mode"])

    def test_handle_chat_once_invalid_agent_mode_type_defaults_to_none(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={
                    "message": "hello",
                    "history": [],
                    "model": "z-ai/glm5",
                    "agent_mode": "true",
                },
            ),
            patch("backend.chat_handlers.chat_once", return_value="ok") as chat_once_mock,
            patch("backend.chat_handlers.send_json"),
        ):
            handle_chat_once(handler, "api-key")

        self.assertIsNone(chat_once_mock.call_args.kwargs["agent_mode"])

    def test_handle_chat_once_invalid_json(self):
        handler = object()
        with (
            patch("backend.chat_handlers.read_json_body", side_effect=json.JSONDecodeError("x", "y", 0)),
            patch("backend.chat_handlers.send_json") as send_json_mock,
        ):
            handle_chat_once(handler, "api-key")

        send_json_mock.assert_called_once_with(handler, 400, {"error": "Invalid JSON body"})

    def test_handle_chat_once_timeout_maps_to_504(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={"message": "hello", "history": []},
            ),
            patch("backend.chat_handlers.chat_once", side_effect=TimeoutError("timed out")),
            patch("backend.chat_handlers.send_json") as send_json_mock,
        ):
            handle_chat_once(handler, "api-key")

        send_json_mock.assert_called_once()
        args = send_json_mock.call_args[0]
        self.assertEqual(args[1], 504)
        self.assertEqual(args[2]["error"], "Upstream request timeout")

    def test_handle_chat_stream_gateway_timeout_emits_error_and_done(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={"message": "hello", "history": []},
            ),
            patch("backend.chat_handlers.init_sse"),
            patch(
                "backend.chat_handlers.stream_chat",
                side_effect=Exception("Error: [504] Gateway Timeout"),
            ),
            patch("backend.chat_handlers.send_sse_event") as send_sse_mock,
        ):
            handle_chat_stream(handler, "api-key")

        self.assertEqual(send_sse_mock.call_count, 2)
        error_call = send_sse_mock.call_args_list[0]
        self.assertEqual(error_call[0][1], {"type": "error", "error": "Upstream gateway timeout"})
        done_call = send_sse_mock.call_args_list[1]
        self.assertEqual(done_call[0][1], {"type": "done", "finish_reason": "error"})

    def test_handle_chat_stream_timeout_emits_error_and_done(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={"message": "hello", "history": []},
            ),
            patch("backend.chat_handlers.init_sse"),
            patch(
                "backend.chat_handlers.stream_chat",
                side_effect=TimeoutError("timed out"),
            ),
            patch("backend.chat_handlers.send_sse_event") as send_sse_mock,
        ):
            handle_chat_stream(handler, "api-key")

        self.assertEqual(send_sse_mock.call_count, 2)
        error_call = send_sse_mock.call_args_list[0]
        self.assertIn("Upstream request timeout", error_call[0][1]["error"])
        done_call = send_sse_mock.call_args_list[1]
        self.assertEqual(done_call[0][1], {"type": "done", "finish_reason": "error"})

    def test_handle_chat_stream_passes_request_id_to_sse_events(self):
        events = [{"type": "token", "content": "hi"}, {"type": "done"}]
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={"message": "hello", "history": [], "request_id": "rid-42"},
            ),
            patch("backend.chat_handlers.init_sse"),
            patch("backend.chat_handlers.stream_chat", return_value=iter(events)),
            patch("backend.chat_handlers.send_sse_event") as send_sse_mock,
        ):
            handle_chat_stream(handler, "api-key")

        self.assertEqual(send_sse_mock.call_count, 2)
        for call in send_sse_mock.call_args_list:
            self.assertEqual(call[1].get("request_id"), "rid-42")

    def test_handle_chat_stream_generic_exception_emits_error_and_done(self):
        handler = object()
        with (
            patch(
                "backend.chat_handlers.read_json_body",
                return_value={"message": "hello", "history": []},
            ),
            patch("backend.chat_handlers.init_sse"),
            patch(
                "backend.chat_handlers.stream_chat",
                side_effect=RuntimeError("something broke"),
            ),
            patch("backend.chat_handlers.send_sse_event") as send_sse_mock,
        ):
            handle_chat_stream(handler, "api-key")

        self.assertEqual(send_sse_mock.call_count, 2)
        self.assertEqual(send_sse_mock.call_args_list[0][0][1]["type"], "error")
        self.assertEqual(send_sse_mock.call_args_list[1][0][1], {"type": "done", "finish_reason": "error"})


if __name__ == "__main__":
    unittest.main()

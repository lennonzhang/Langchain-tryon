import json
import io
from urllib import error as urlerror
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from backend.proxy_chat_model import (
    ProxyGatewayChatModel,
    _detail_from_exception,
    _iter_sse_events,
    _json_post,
    _messages_to_role_content,
    _safe_json_loads,
)


class _FakeHttpResponse:
    def __init__(self, body: bytes, lines: list[bytes] | None = None):
        self._body = body
        self._lines = lines or []

    def read(self):
        return self._body

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _openai_sse_lines(completed_response: dict) -> list[bytes]:
    """Build SSE lines wrapping a completed response object."""
    event = {"type": "response.completed", "response": completed_response}
    return [f'data: {json.dumps(event)}\n'.encode("utf-8")]


class TestProxyChatModel(unittest.TestCase):
    def test_anthropic_messages_response_parsed(self):
        payload = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }
        model = ProxyGatewayChatModel(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(json.dumps(payload).encode("utf-8")),
        ):
            out = model.invoke([HumanMessage(content="hi")])
        self.assertEqual(out.content, "hello")

    def test_openai_responses_parsed_reasoning_and_text(self):
        completed = {
            "id": "resp_1",
            "model": "gpt-5.3-codex",
            "output": [
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "think"}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "answer"}],
                },
            ],
            "usage": {"input_tokens": 12, "output_tokens": 5},
        }
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
            thinking_mode=True,
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=_openai_sse_lines(completed)),
        ):
            out = model.invoke([HumanMessage(content="hi")])
        self.assertEqual(out.content, "answer")
        self.assertEqual(out.additional_kwargs.get("reasoning_content"), "think")

    def test_google_generate_content_parsed(self):
        payload = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "gemini answer"}], "role": "model"},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3},
            "modelVersion": "gemini-3-pro-preview",
        }
        model = ProxyGatewayChatModel(
            provider="google",
            model="gemini-3-pro-preview",
            api_key="k",
            base_url="https://x/api/v1beta",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(json.dumps(payload).encode("utf-8")),
        ):
            out = model.invoke([HumanMessage(content="hi")])
        self.assertEqual(out.content, "gemini answer")

    def test_google_request_includes_generation_config(self):
        payload = {
            "candidates": [
                {"content": {"parts": [{"text": "ok"}], "role": "model"}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

        model = ProxyGatewayChatModel(
            provider="google",
            model="gemini-3-pro-preview",
            api_key="k",
            base_url="https://x/api/v1beta",
            temperature=0.5,
            top_p=0.9,
            max_completion_tokens=2048,
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            model.invoke([HumanMessage(content="hi")])

        gen_config = captured["body"].get("generationConfig", {})
        self.assertEqual(gen_config["temperature"], 0.5)
        self.assertEqual(gen_config["topP"], 0.9)
        self.assertEqual(gen_config["maxOutputTokens"], 2048)

    def test_google_system_prompt_uses_system_instruction(self):
        payload = {
            "candidates": [
                {"content": {"parts": [{"text": "ok"}], "role": "model"}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

        model = ProxyGatewayChatModel(
            provider="google",
            model="gemini-3-pro-preview",
            api_key="k",
            base_url="https://x/api/v1beta",
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            model.invoke([SystemMessage(content="You are helpful."), HumanMessage(content="hi")])

        body = captured["body"]
        self.assertIn("systemInstruction", body)
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "You are helpful.")
        # system prompt should NOT appear in contents
        for c in body["contents"]:
            self.assertNotEqual(c.get("role"), "system")

    def test_openai_stream_sse_parsed_to_chunks(self):
        lines = [
            b'data: {"type":"response.reasoning_summary_text.delta","delta":"r1"}\n',
            b'data: {"type":"response.output_text.delta","delta":"a1"}\n',
            b'data: {"type":"response.completed","response":{"output":[]}}\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))
        self.assertTrue(any(c.additional_kwargs.get("reasoning_content") == "r1" for c in chunks))
        self.assertTrue(any(c.content == "a1" for c in chunks))

    def test_openai_stream_no_double_text_when_deltas_present(self):
        """When delta events are emitted, response.completed should NOT re-emit the same text."""
        completed_resp = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "full answer"}],
                }
            ]
        }
        lines = [
            b'data: {"type":"response.output_text.delta","delta":"full "}\n',
            b'data: {"type":"response.output_text.delta","delta":"answer"}\n',
            f'data: {json.dumps({"type": "response.completed", "response": completed_resp})}\n'.encode("utf-8"),
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))
        text = "".join(c.content for c in chunks)
        self.assertEqual(text, "full answer")  # not "full answerfull answer"

    def test_openai_tools_payload_uses_responses_shape(self):
        completed = {
            "id": "resp_1",
            "model": "gpt-5.3-codex",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "web_search",
                    "arguments": "{\"query\":\"q\"}",
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=_openai_sse_lines(completed))

        def web_search(query: str) -> str:
            return query

        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        ).bind_tools([web_search])

        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            out = model.invoke([HumanMessage(content="hi")])

        tools = captured["body"]["tools"]
        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["name"], "web_search")
        self.assertIn("parameters", tools[0])
        self.assertEqual(out.tool_calls[0]["name"], "web_search")

    def test_openai_invoke_multiline_sse_event_parsed(self):
        lines = [
            b'event: response.completed\n',
            b'data: {"type":"response.completed",\n',
            b'data: "response":{"model":"gpt-5.3-codex","output":[{"type":"message","content":[{"type":"output_text","text":"ok"}]}],"usage":{"input_tokens":1,"output_tokens":1}}}\n',
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])
        self.assertEqual(out.content, "ok")

    def test_openai_invoke_missing_completed_includes_last_event_context(self):
        lines = [
            b'data: {"type":"response.output_text.delta","delta":"partial"}\n',
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b"", lines=lines),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            model.invoke([HumanMessage(content="hi")])

        msg = str(ctx.exception)
        self.assertIn("provider=openai", msg)
        self.assertIn("protocol=openai_responses", msg)
        self.assertIn("missing response.completed", msg)

    def test_openai_stream_event_error_is_normalized(self):
        lines = [
            b'data: {"type":"error","error":{"type":"request_error","message":"boom"}}\n',
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b"", lines=lines),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            list(model.stream([HumanMessage(content="hi")]))

        msg = str(ctx.exception)
        self.assertIn("provider=openai", msg)
        self.assertIn("protocol=openai_responses", msg)
        self.assertIn("boom", msg)

    def test_json_post_empty_body_raises_diagnostic(self):
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b""),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            _json_post(
                "https://x/api/v1/messages",
                headers={"Content-Type": "application/json"},
                body={"a": 1},
                timeout_s=5,
                model_id="anthropic/claude-sonnet-4-6",
            )
        self.assertIn("empty upstream body", str(ctx.exception))

    def test_json_post_non_json_body_raises_diagnostic(self):
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b"<html>oops</html>"),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            _json_post(
                "https://x/api/v1/messages",
                headers={"Content-Type": "application/json"},
                body={"a": 1},
                timeout_s=5,
                model_id="anthropic/claude-sonnet-4-6",
            )
        self.assertIn("non-json upstream body", str(ctx.exception))

    def test_anthropic_stream_http_and_non_http_errors_normalized(self):
        http_err = urlerror.HTTPError(
            url="https://x/api/v1/messages",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(
                b'{"type":"error","error":{"type":"invalid_request_error","message":"bad anthropic"}}',
            ),
        )

        model = ProxyGatewayChatModel(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with (
            patch("backend.proxy_chat_model.request.urlopen", side_effect=http_err),
            self.assertRaises(RuntimeError) as ctx_http,
        ):
            list(model.stream([HumanMessage(content="hi")]))
        self.assertIn("provider=anthropic", str(ctx_http.exception))
        self.assertIn("protocol=anthropic_messages", str(ctx_http.exception))

        lines = [
            b'data: {"type":"error","error":{"message":"stream fail"}}\n',
            b'\n',
        ]
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b"", lines=lines),
            ),
            self.assertRaises(RuntimeError) as ctx_non_http,
        ):
            list(model.stream([HumanMessage(content="hi")]))
        self.assertIn("provider=anthropic", str(ctx_non_http.exception))
        self.assertIn("stream fail", str(ctx_non_http.exception))

    def test_google_stream_http_and_non_http_errors_normalized(self):
        http_err = urlerror.HTTPError(
            url="https://x/api/v1beta/models/gemini:streamGenerateContent?alt=sse",
            code=500,
            msg="Internal",
            hdrs=None,
            fp=io.BytesIO(
                b'{"type":"error","error":{"type":"internal_error","message":"bad google"}}',
            ),
        )

        model = ProxyGatewayChatModel(
            provider="google",
            model="gemini-3-pro-preview",
            api_key="k",
            base_url="https://x/api/v1beta",
        )
        with (
            patch("backend.proxy_chat_model.request.urlopen", side_effect=http_err),
            self.assertRaises(RuntimeError) as ctx_http,
        ):
            list(model.stream([HumanMessage(content="hi")]))
        self.assertIn("provider=google", str(ctx_http.exception))
        self.assertIn("protocol=google_generate_content", str(ctx_http.exception))

        lines = [b'data: {"error":{"message":"stream google fail"}}\n', b'\n']
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b"", lines=lines),
            ),
            self.assertRaises(RuntimeError) as ctx_non_http,
        ):
            list(model.stream([HumanMessage(content="hi")]))
        self.assertIn("provider=google", str(ctx_non_http.exception))
        self.assertIn("stream google fail", str(ctx_non_http.exception))

    def test_openai_body_omits_temperature_top_p(self):
        """OpenAI Responses API does not accept temperature/top_p as top-level fields."""
        completed = {
            "model": "gpt-5.3-codex",
            "output": [
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]},
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=_openai_sse_lines(completed))

        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
            temperature=0.3,
            top_p=0.8,
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            model.invoke([HumanMessage(content="hi")])

        self.assertNotIn("temperature", captured["body"])
        self.assertNotIn("top_p", captured["body"])


    # ── Anthropic streaming tests ──

    def test_anthropic_stream_text_deltas(self):
        lines = [
            b'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6"}}\n',
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n',
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n',
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}\n',
            b'data: {"type":"content_block_stop","index":0}\n',
            b'data: {"type":"message_stop"}\n',
        ]
        model = ProxyGatewayChatModel(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))
        text = "".join(c.content for c in chunks)
        self.assertEqual(text, "Hello world")

    def test_anthropic_stream_thinking_deltas(self):
        lines = [
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"step1"}}\n',
            b'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"answer"}}\n',
            b'data: {"type":"message_stop"}\n',
        ]
        model = ProxyGatewayChatModel(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))
        self.assertTrue(any(c.additional_kwargs.get("reasoning_content") == "step1" for c in chunks))
        self.assertTrue(any(c.content == "answer" for c in chunks))

    def test_anthropic_stream_sends_stream_true(self):
        lines = [
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n',
            b'data: {"type":"message_stop"}\n',
        ]
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=lines)

        model = ProxyGatewayChatModel(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            list(model.stream([HumanMessage(content="hi")]))
        self.assertTrue(captured["body"]["stream"])

    # ── Google streaming tests ──

    def test_google_stream_text_chunks(self):
        lines = [
            b'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}],"role":"model"}}]}\n',
            b'data: {"candidates":[{"content":{"parts":[{"text":" there"}],"role":"model"},"finishReason":"STOP"}]}\n',
        ]
        model = ProxyGatewayChatModel(
            provider="google",
            model="gemini-3-pro-preview",
            api_key="k",
            base_url="https://x/api/v1beta",
        )
        with patch(
            "backend.proxy_chat_model.request.urlopen",
            return_value=_FakeHttpResponse(b"", lines=lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))
        text = "".join(c.content for c in chunks)
        self.assertEqual(text, "Hello there")

    def test_google_stream_uses_stream_endpoint(self):
        lines = [
            b'data: {"candidates":[{"content":{"parts":[{"text":"ok"}],"role":"model"},"finishReason":"STOP"}]}\n',
        ]
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=lines)

        model = ProxyGatewayChatModel(
            provider="google",
            model="gemini-3-pro-preview",
            api_key="k",
            base_url="https://x/api/v1beta",
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            list(model.stream([HumanMessage(content="hi")]))

        self.assertIn("streamGenerateContent", captured["url"])
        self.assertIn("alt=sse", captured["url"])
        self.assertIn("generationConfig", captured["body"])
        self.assertNotIn("streamGenerateContent", captured["url"].split("models/")[0])


    # ── P0: Bug fix validation ──

    def test_openai_body_always_includes_reasoning(self):
        """Proxy requires reasoning field; verify present for both thinking modes."""
        completed = {
            "model": "gpt-5.3-codex",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        for thinking, expected_effort in [(True, "high"), (False, "low")]:
            captured = {}

            def _fake_urlopen(req, timeout=0):  # noqa: ARG001
                captured["body"] = json.loads(req.data.decode("utf-8"))
                return _FakeHttpResponse(b"", lines=_openai_sse_lines(completed))

            model = ProxyGatewayChatModel(
                provider="openai", model="gpt-5.3-codex", api_key="k",
                base_url="https://x/api/v1", thinking_mode=thinking,
            )
            with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
                model.invoke([HumanMessage(content="hi")])

            reasoning = captured["body"].get("reasoning")
            self.assertIsNotNone(reasoning, f"reasoning missing when thinking_mode={thinking}")
            self.assertEqual(reasoning["effort"], expected_effort)
            self.assertEqual(reasoning["summary"], "auto")

    def test_openai_body_has_no_extra_fields(self):
        """Golden body test: only expected top-level keys are present."""
        completed = {
            "model": "gpt-5.3-codex",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=_openai_sse_lines(completed))

        model = ProxyGatewayChatModel(
            provider="openai", model="gpt-5.3-codex", api_key="k",
            base_url="https://x/api/v1", thinking_mode=True,
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            model.invoke([HumanMessage(content="hi")])

        allowed = {"model", "input", "store", "stream", "text", "reasoning", "tools", "tool_choice"}
        extra = set(captured["body"].keys()) - allowed
        self.assertEqual(extra, set(), f"Unexpected fields in OpenAI body: {extra}")


class TestIterSseEvents(unittest.TestCase):
    """Direct unit tests for the SSE parser."""

    def test_basic_single_event(self):
        lines = [b"data: {\"a\":1}\n", b"\n"]
        events = list(_iter_sse_events(iter(lines)))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"], '{"a":1}')

    def test_multiline_data_joined(self):
        lines = [
            b"event: foo\n",
            b"data: line1\n",
            b"data: line2\n",
            b"\n",
        ]
        events = list(_iter_sse_events(iter(lines)))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "foo")
        self.assertIn("line1", events[0]["data"])
        self.assertIn("line2", events[0]["data"])

    def test_comment_lines_ignored(self):
        lines = [b": this is a comment\n", b"data: real\n", b"\n"]
        events = list(_iter_sse_events(iter(lines)))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"], "real")

    def test_no_blank_separator_produces_separate_events(self):
        """Gateway quirk: consecutive data: lines without blank produce separate events."""
        lines = [
            b"data: first\n",
            b"data: second\n",
        ]
        events = list(_iter_sse_events(iter(lines)))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["data"], "first")
        self.assertEqual(events[1]["data"], "second")

    def test_empty_stream(self):
        events = list(_iter_sse_events(iter([])))
        self.assertEqual(events, [])

    def test_done_marker_yields_as_data(self):
        lines = [b"data: [DONE]\n", b"\n"]
        events = list(_iter_sse_events(iter(lines)))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"], "[DONE]")


class TestDispatchEdgeCases(unittest.TestCase):

    def test_generate_unsupported_provider_raises(self):
        model = ProxyGatewayChatModel(
            provider="unknown", model="m", api_key="k", base_url="https://x",
        )
        with self.assertRaises(RuntimeError) as ctx:
            model.invoke([HumanMessage(content="hi")])
        self.assertIn("Unsupported proxy provider", str(ctx.exception))

    def test_stream_unsupported_provider_raises(self):
        model = ProxyGatewayChatModel(
            provider="unknown", model="m", api_key="k", base_url="https://x",
        )
        with self.assertRaises(RuntimeError) as ctx:
            list(model.stream([HumanMessage(content="hi")]))
        self.assertIn("Unsupported proxy provider", str(ctx.exception))

    def test_anthropic_stream_body_includes_system(self):
        lines = [
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n',
            b'data: {"type":"message_stop"}\n',
        ]
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=lines)

        model = ProxyGatewayChatModel(
            provider="anthropic", model="claude-sonnet-4-6", api_key="k",
            base_url="https://x/api/v1",
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            list(model.stream([SystemMessage(content="Be brief."), HumanMessage(content="hi")]))

        self.assertIn("system", captured["body"])
        self.assertEqual(captured["body"]["system"], "Be brief.")
        # system should not appear in messages array
        for m in captured["body"]["messages"]:
            self.assertNotEqual(m.get("role"), "system")

    def test_openai_thinking_false_reasoning_low(self):
        lines = [
            b'data: {"type":"response.output_text.delta","delta":"ok"}\n',
            b'data: {"type":"response.completed","response":{"output":[]}}\n',
        ]
        captured = {}

        def _fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeHttpResponse(b"", lines=lines)

        model = ProxyGatewayChatModel(
            provider="openai", model="gpt-5.3-codex", api_key="k",
            base_url="https://x/api/v1", thinking_mode=False,
        )
        with patch("backend.proxy_chat_model.request.urlopen", side_effect=_fake_urlopen):
            list(model.stream([HumanMessage(content="hi")]))

        self.assertEqual(captured["body"]["reasoning"]["effort"], "low")


class TestUtilityFunctions(unittest.TestCase):

    def test_messages_to_role_content_tool_message(self):
        tool_msg = ToolMessage(content="result data", tool_call_id="call_1", name="web_search")
        mapped, system = _messages_to_role_content([tool_msg])
        self.assertEqual(system, "")
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["role"], "user")
        self.assertIn("web_search", mapped[0]["content"])
        self.assertIn("result data", mapped[0]["content"])

    def test_detail_from_exception_passthrough(self):
        already_normalized = "provider=openai | protocol=openai_responses | type=error | message=boom"
        result = _detail_from_exception("openai/gpt-5.3-codex", RuntimeError(already_normalized))
        self.assertEqual(result, already_normalized)

    def test_detail_from_exception_normalizes_raw(self):
        result = _detail_from_exception("openai/gpt-5.3-codex", RuntimeError("connection reset"))
        self.assertIn("provider=openai", result)
        self.assertIn("protocol=openai_responses", result)

    def test_json_post_http_error_with_model_id(self):
        http_err = urlerror.HTTPError(
            url="https://x/api/v1/responses",
            code=500,
            msg="Internal",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"type":"server_error","message":"fail"}}'),
        )
        with (
            patch("backend.proxy_chat_model.request.urlopen", side_effect=http_err),
            self.assertRaises(RuntimeError) as ctx,
        ):
            _json_post("https://x/api/v1/responses", {}, {}, 5, model_id="openai/gpt-5.3-codex")
        self.assertIn("provider=openai", str(ctx.exception))
        self.assertIn("status=500", str(ctx.exception))

    def test_json_post_http_error_without_model_id(self):
        http_err = urlerror.HTTPError(
            url="https://x/api/v1/messages",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'raw error body'),
        )
        with (
            patch("backend.proxy_chat_model.request.urlopen", side_effect=http_err),
            self.assertRaises(RuntimeError) as ctx,
        ):
            _json_post("https://x/api/v1/messages", {}, {}, 5, model_id="")
        msg = str(ctx.exception)
        self.assertIn("raw error body", msg)
        self.assertNotIn("provider=", msg)

    def test_bind_tools_returns_copy(self):
        original = ProxyGatewayChatModel(
            provider="openai", model="gpt-5.3-codex", api_key="k",
            base_url="https://x/api/v1",
        )

        def dummy_tool(query: str) -> str:
            """Search the web."""
            return query

        bound = original.bind_tools([dummy_tool], tool_choice="auto")
        self.assertEqual(len(original.bound_tools), 0)
        self.assertIsNone(original.tool_choice)
        self.assertTrue(len(bound.bound_tools) > 0)
        self.assertEqual(bound.tool_choice, "auto")

    def test_safe_json_loads_dict_passthrough(self):
        self.assertEqual(_safe_json_loads({"a": 1}), {"a": 1})

    def test_safe_json_loads_valid_json_string(self):
        self.assertEqual(_safe_json_loads('{"b": 2}'), {"b": 2})

    def test_safe_json_loads_invalid_json_string(self):
        self.assertEqual(_safe_json_loads("not json"), {"value": "not json"})

    def test_safe_json_loads_non_string(self):
        self.assertEqual(_safe_json_loads(42), {})
        self.assertEqual(_safe_json_loads(None), {})


class TestParseEdgeCases(unittest.TestCase):

    def test_parse_openai_completed_empty_output(self):
        text, reasoning, tools, usage = ProxyGatewayChatModel._parse_openai_completed({"output": []})
        self.assertEqual(text, [])
        self.assertEqual(reasoning, [])
        self.assertEqual(tools, [])
        self.assertEqual(usage, {})

    def test_parse_openai_completed_malformed_items(self):
        data = {"output": ["not a dict", 42, None, {"type": "unknown_type"}]}
        text, reasoning, tools, usage = ProxyGatewayChatModel._parse_openai_completed(data)
        self.assertEqual(text, [])
        self.assertEqual(reasoning, [])
        self.assertEqual(tools, [])

    def test_openai_stream_completed_fallback_no_deltas_no_text(self):
        """No text deltas and completed has empty output — LangChain raises ValueError."""
        completed_resp = {"output": []}
        lines = [
            f'data: {json.dumps({"type": "response.completed", "response": completed_resp})}\n'.encode("utf-8"),
        ]
        model = ProxyGatewayChatModel(
            provider="openai", model="gpt-5.3-codex", api_key="k",
            base_url="https://x/api/v1",
        )
        with (
            patch(
                "backend.proxy_chat_model.request.urlopen",
                return_value=_FakeHttpResponse(b"", lines=lines),
            ),
            self.assertRaises(ValueError),
        ):
            list(model.stream([HumanMessage(content="hi")]))


class TestSseParseLogging(unittest.TestCase):
    """Verify that malformed SSE events produce a warning log."""

    def test_anthropic_stream_logs_malformed_event(self):
        model = ProxyGatewayChatModel(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="test-key",
            base_url="https://example.com/api/v1",
        )
        # SSE with one malformed data line followed by message_stop
        lines = [
            b"data: {not valid json}\n",
            b"\n",
            b'data: {"type":"message_stop"}\n',
            b"\n",
        ]
        fake_resp = _FakeHttpResponse(b"", lines=lines)
        with (
            patch("backend.proxy_chat_model.request.urlopen", return_value=fake_resp),
            patch("backend.proxy_chat_model.logger.warning") as warn_mock,
        ):
            # Stream produces no valid chunks, so LangChain raises ValueError
            try:
                list(model.stream([HumanMessage(content="hi")]))
            except ValueError:
                pass
        warn_mock.assert_called()
        self.assertIn("malformed", warn_mock.call_args[0][0].lower())


if __name__ == "__main__":
    unittest.main()

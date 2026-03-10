import json
import io
import httpx
from urllib import error as urlerror
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

import backend.infrastructure.protocols.anthropic_messages as _anthropic_messages

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


class _FakeOpenAISseContext:
    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __enter__(self):
        return iter(self._lines)

    def __exit__(self, exc_type, exc, tb):
        return False


def _fake_openai_sse(lines: list[bytes], captured: dict | None = None, exc: Exception | None = None):
    def _factory(config, body, headers):
        if captured is not None:
            captured["body"] = body
            captured["headers"] = headers
            captured["url"] = f"{config.base_url.rstrip('/')}/responses"
        if exc is not None:
            raise exc
        return _FakeOpenAISseContext(lines)

    return _factory


class TestProxyChatModel(unittest.TestCase):
    def test_anthropic_messages_response_parsed(self):
        payload = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [
                {"type": "thinking", "thinking": "plan"},
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "id": "tool_1", "name": "web_search", "input": {"query": "q"}},
            ],
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
        self.assertEqual(out.additional_kwargs.get("reasoning_content"), "plan")
        self.assertEqual(out.tool_calls[0]["name"], "web_search")
        self.assertEqual(out.tool_calls[0]["args"], {"query": "q"})

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
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(_openai_sse_lines(completed)),
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
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
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
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
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

        def web_search(query: str) -> str:
            return query

        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        ).bind_tools([web_search])

        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(_openai_sse_lines(completed), captured),
        ):
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
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
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
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse(lines),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            model.invoke([HumanMessage(content="hi")])

        msg = str(ctx.exception)
        self.assertIn("provider=openai", msg)
        self.assertIn("protocol=openai_responses", msg)
        self.assertIn("missing response.completed", msg)

    def test_openai_invoke_recovers_from_output_item_when_completed_missing(self):
        lines = [
            (
                b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n'
            ),
            b'\n',
            (
                b'data: {"type":"response.output_item.added","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"recovered answer"}'
                b']}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.content, "recovered answer")

    def test_openai_invoke_prefers_completed_over_output_item_snapshots(self):
        completed = {
            "model": "gpt-5.3-codex",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "final answer"}],
                }
            ],
            "usage": {"input_tokens": 2, "output_tokens": 3},
        }
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.done","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"stale answer"}'
                b']}}\n'
            ),
            b'\n',
            f'data: {json.dumps({"type": "response.completed", "response": completed})}\n'.encode("utf-8"),
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.content, "final answer")

    def test_openai_invoke_orders_output_items_by_output_index(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.done","output_index":1,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"second"}'
                b']}}\n'
            ),
            b'\n',
            (
                b'data: {"type":"response.output_item.done","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"first "}'
                b']}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.content, "first second")

    def test_openai_invoke_recovers_tool_call_from_output_item_done(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.done","output_index":0,'
                b'"item":{"type":"function_call","call_id":"call_1","name":"web_search",'
                b'"arguments":"{\\"query\\":\\"q\\"}"}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.tool_calls[0]["name"], "web_search")
        self.assertEqual(out.tool_calls[0]["args"], {"query": "q"})

    def test_openai_stream_recovers_text_from_output_items_when_completed_missing(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.done","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"fallback answer"}'
                b']}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))

        self.assertEqual("".join(c.content for c in chunks), "fallback answer")

    def test_openai_stream_no_double_text_when_deltas_and_output_items_both_exist(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            b'data: {"type":"response.output_text.delta","delta":"full "}\n',
            b'data: {"type":"response.output_text.delta","delta":"answer"}\n',
            (
                b'data: {"type":"response.output_item.done","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"full answer"}'
                b']}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))

        self.assertEqual("".join(c.content for c in chunks), "full answer")

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
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse(lines),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            list(model.stream([HumanMessage(content="hi")]))

        msg = str(ctx.exception)
        self.assertIn("provider=openai", msg)
        self.assertIn("protocol=openai_responses", msg)
        self.assertIn("type=request_error", msg)
        self.assertIn("boom", msg)

    def test_openai_invoke_event_error_is_normalized(self):
        lines = [
            b'data: {"type":"error","error":{"type":"request_error","message":"invoke boom"}}\n',
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
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse(lines),
            ),
            self.assertRaises(RuntimeError) as ctx,
        ):
            model.invoke([HumanMessage(content="hi")])

        msg = str(ctx.exception)
        self.assertIn("provider=openai", msg)
        self.assertIn("protocol=openai_responses", msg)
        self.assertIn("type=request_error", msg)
        self.assertIn("invoke boom", msg)

    def test_openai_invoke_merges_multiple_added_events_for_same_message_item(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.added","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"hello "},'
                b'{"type":"output_text","text":""}'
                b']}}\n'
            ),
            b'\n',
            (
                b'data: {"type":"response.output_item.added","output_index":0,'
                b'"item":{"type":"message","content":['
                b'{},'
                b'{"type":"output_text","text":"world"}'
                b']}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.content, "hello world")

    def test_openai_invoke_done_merges_with_added_for_tool_call(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.added","output_index":0,'
                b'"item":{"type":"function_call","call_id":"call_1","name":"web_search",'
                b'"arguments":"{\\"query\\":\\"wea"}}\n'
            ),
            b'\n',
            (
                b'data: {"type":"response.output_item.done","output_index":0,'
                b'"item":{"type":"function_call","call_id":"call_1",'
                b'"arguments":"{\\"query\\":\\"weather\\"}"}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.tool_calls[0]["name"], "web_search")
        self.assertEqual(out.tool_calls[0]["args"], {"query": "weather"})

    def test_openai_invoke_keeps_first_seen_order_without_output_index(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.done","item":{"id":"b_item","type":"message",'
                b'"role":"assistant","content":[{"type":"output_text","text":"first "}]}}\n'
            ),
            b'\n',
            (
                b'data: {"type":"response.output_item.done","item":{"id":"a_item","type":"message",'
                b'"role":"assistant","content":[{"type":"output_text","text":"second"}]}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            out = model.invoke([HumanMessage(content="hi")])

        self.assertEqual(out.content, "first second")

    def test_openai_stream_replays_only_new_suffix_from_output_item_snapshots(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.3-codex"}}\n',
            b'\n',
            (
                b'data: {"type":"response.output_item.added","output_index":0,'
                b'"item":{"type":"message","role":"assistant","content":['
                b'{"type":"output_text","text":"hello "},'
                b'{"type":"output_text","text":""}'
                b']}}\n'
            ),
            b'\n',
            (
                b'data: {"type":"response.output_item.added","output_index":0,'
                b'"item":{"type":"message","content":['
                b'{},'
                b'{"type":"output_text","text":"world"}'
                b']}}\n'
            ),
            b'\n',
        ]
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines),
        ):
            chunks = list(model.stream([HumanMessage(content="hi")]))

        self.assertEqual([chunk.content for chunk in chunks if chunk.content], ["hello ", "world"])

    def test_openai_invoke_timeout_is_preserved_as_timeout_error(self):
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with (
            patch(
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse([], exc=httpx.ReadTimeout("The read operation timed out")),
            ),
            self.assertRaises(TimeoutError),
        ):
            model.invoke([HumanMessage(content="hi")])

    def test_openai_stream_timeout_is_preserved_as_timeout_error(self):
        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
        )
        with (
            patch(
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse([], exc=httpx.ReadTimeout("The read operation timed out")),
            ),
            self.assertRaises(TimeoutError),
        ):
            list(model.stream([HumanMessage(content="hi")]))

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

        model = ProxyGatewayChatModel(
            provider="openai",
            model="gpt-5.3-codex",
            api_key="k",
            base_url="https://x/api/v1",
            temperature=0.3,
            top_p=0.8,
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(_openai_sse_lines(completed), captured),
        ):
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

    def test_anthropic_stream_recovers_text_at_eof_without_message_stop(self):
        lines = [
            b'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6"}}\n',
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n',
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Recovered"}}\n',
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

        self.assertEqual("".join(c.content for c in chunks), "Recovered")

    def test_anthropic_stream_recovers_text_from_started_block_when_no_text_deltas_emitted(self):
        lines = [
            b'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6"}}\n',
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":"Final snapshot"}}\n',
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

        self.assertEqual("".join(c.content for c in chunks), "Final snapshot")

    def test_anthropic_stream_orders_started_text_blocks_by_index(self):
        lines = [
            b'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6"}}\n',
            b'data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":"second"}}\n',
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":"first "}}\n',
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

        self.assertEqual("".join(c.content for c in chunks), "first second")

    def test_anthropic_stream_no_false_text_recovery_for_thinking_only_eof(self):
        lines = [
            b'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6"}}\n',
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}\n',
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"step1"}}\n',
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
            try:
                chunks = list(model.stream([HumanMessage(content="hi")]))
            except ValueError:
                chunks = []

        self.assertEqual("".join(c.content for c in chunks), "")
        self.assertTrue(any(c.additional_kwargs.get("reasoning_content") == "step1" for c in chunks))

    def test_anthropic_stream_tool_use_partial_json_is_not_emitted_as_text(self):
        lines = [
            b'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6"}}\n',
            b'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"tool_1","name":"web_search"}}\n',
            b'data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"query\\":\\"hel"}}\n',
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
            try:
                chunks = list(model.stream([HumanMessage(content="hi")]))
            except ValueError:
                chunks = []

        self.assertEqual("".join(c.content for c in chunks), "")

    def test_anthropic_invoke_tool_use_json_blocks_are_parsed(self):
        payload = {
            "id": "msg_456",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [
                {"type": "tool_use", "id": "tool_2", "name": "read_url", "input": {"url": "https://example.com"}},
            ],
            "usage": {"input_tokens": 11, "output_tokens": 2},
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

        self.assertEqual(out.tool_calls[0]["name"], "read_url")
        self.assertEqual(out.tool_calls[0]["args"], {"url": "https://example.com"})

    def test_anthropic_accumulator_recovers_complete_tool_use_at_eof(self):
        accumulator = _anthropic_messages._AnthropicStreamAccumulator()
        accumulator.add_event({
            "type": "message_start",
            "message": {"id": "msg_1", "model": "claude-sonnet-4-6"},
        })
        accumulator.add_event({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tool_1", "name": "web_search"},
        })
        accumulator.add_event({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": "{\"query\":\"weather\"}"},
        })

        blocks = accumulator.final_blocks(allow_eof_fallback=True)
        self.assertIsNotNone(blocks)
        self.assertEqual(blocks[0]["type"], "tool_use")
        self.assertEqual(blocks[0]["input"], {"query": "weather"})

    def test_anthropic_accumulator_does_not_recover_incomplete_tool_use_at_eof(self):
        accumulator = _anthropic_messages._AnthropicStreamAccumulator()
        accumulator.add_event({
            "type": "message_start",
            "message": {"id": "msg_1", "model": "claude-sonnet-4-6"},
        })
        accumulator.add_event({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tool_1", "name": "web_search"},
        })
        accumulator.add_event({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": "{\"query\":\"wea"},
        })

        self.assertIsNone(accumulator.final_blocks(allow_eof_fallback=True))

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

            model = ProxyGatewayChatModel(
                provider="openai", model="gpt-5.3-codex", api_key="k",
                base_url="https://x/api/v1", thinking_mode=thinking,
            )
            with patch(
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse(_openai_sse_lines(completed), captured),
            ):
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

        model = ProxyGatewayChatModel(
            provider="openai", model="gpt-5.3-codex", api_key="k",
            base_url="https://x/api/v1", thinking_mode=True,
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(_openai_sse_lines(completed), captured),
        ):
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

        model = ProxyGatewayChatModel(
            provider="openai", model="gpt-5.3-codex", api_key="k",
            base_url="https://x/api/v1", thinking_mode=False,
        )
        with patch(
            "backend.infrastructure.protocols.openai_responses._post_responses_sse",
            side_effect=_fake_openai_sse(lines, captured),
        ):
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
                "backend.infrastructure.protocols.openai_responses._post_responses_sse",
                side_effect=_fake_openai_sse(lines),
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


class TestAnthropicToolUseInputFallback(unittest.TestCase):
    """§2: tool_use blocks with non-dict input should be kept with args={}."""

    def test_tool_use_input_null_preserved_with_empty_args(self):
        from backend.infrastructure.protocols.anthropic_messages import _parse_anthropic_content_blocks

        blocks = [
            {"type": "text", "text": "calling tool"},
            {"type": "tool_use", "id": "t1", "name": "search", "input": None},
        ]
        text_parts, _reasoning, tool_calls = _parse_anthropic_content_blocks(blocks)
        self.assertEqual(text_parts, ["calling tool"])
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "search")
        self.assertEqual(tool_calls[0]["args"], {})

    def test_tool_use_input_string_preserved_with_empty_args(self):
        from backend.infrastructure.protocols.anthropic_messages import _parse_anthropic_content_blocks

        blocks = [
            {"type": "tool_use", "id": "t2", "name": "fetch", "input": "bad"},
        ]
        _text, _reasoning, tool_calls = _parse_anthropic_content_blocks(blocks)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["args"], {})

    def test_tool_use_input_dict_passes_through(self):
        from backend.infrastructure.protocols.anthropic_messages import _parse_anthropic_content_blocks

        blocks = [
            {"type": "tool_use", "id": "t3", "name": "calc", "input": {"x": 1}},
        ]
        _text, _reasoning, tool_calls = _parse_anthropic_content_blocks(blocks)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["args"], {"x": 1})


class TestMergeValuesOptimization(unittest.TestCase):
    """§4a: _merge_values scalar fast-path and edge cases."""

    def test_scalar_merge_returns_same_object(self):
        from backend.infrastructure.protocols.openai_responses import _merge_values

        result = _merge_values(None, 42, path=(), incoming_has_priority=True, incoming_higher_precedence=False)
        self.assertEqual(result, 42)

        result = _merge_values("hello", None, path=(), incoming_has_priority=True, incoming_higher_precedence=False)
        self.assertEqual(result, "hello")

    def test_nested_dict_merge(self):
        from backend.infrastructure.protocols.openai_responses import _merge_values

        existing = {"a": {"b": 1, "c": 2}, "d": 3}
        incoming = {"a": {"b": 10, "e": 5}}
        result = _merge_values(existing, incoming, path=(), incoming_has_priority=True, incoming_higher_precedence=False)
        self.assertEqual(result["a"]["b"], 10)
        self.assertEqual(result["a"]["c"], 2)
        self.assertEqual(result["a"]["e"], 5)
        self.assertEqual(result["d"], 3)

    def test_list_merge_different_lengths(self):
        from backend.infrastructure.protocols.openai_responses import _merge_values

        existing = [1, 2]
        incoming = [10, 20, 30]
        result = _merge_values(existing, incoming, path=(), incoming_has_priority=True, incoming_higher_precedence=False)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[2], 30)

    def test_immutable_scalar_not_deepcopied(self):
        from backend.infrastructure.protocols.openai_responses import _merge_values

        result = _merge_values(None, True, path=(), incoming_has_priority=True, incoming_higher_precedence=False)
        self.assertIs(result, True)

        result = _merge_values(None, 3.14, path=(), incoming_has_priority=True, incoming_higher_precedence=False)
        self.assertEqual(result, 3.14)


if __name__ == "__main__":
    unittest.main()

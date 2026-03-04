import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.http_utils import PayloadTooLargeError, read_json_body, send_sse_event, serve_static


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler with a writable wfile."""

    def __init__(self):
        self.wfile = io.BytesIO()

    def read_events(self) -> list[dict]:
        raw = self.wfile.getvalue().decode("utf-8")
        events = []
        for block in raw.split("\n\n"):
            block = block.strip()
            if block.startswith("data:"):
                events.append(json.loads(block[5:].strip()))
        return events


class TestSendSseEvent(unittest.TestCase):
    def test_injects_version_field(self):
        handler = FakeHandler()
        send_sse_event(handler, {"type": "token", "content": "hi"})

        events = handler.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["v"], 1)
        self.assertEqual(events[0]["type"], "token")
        self.assertEqual(events[0]["content"], "hi")

    def test_injects_request_id_when_provided(self):
        handler = FakeHandler()
        send_sse_event(handler, {"type": "done"}, request_id="abc-123")

        events = handler.read_events()
        self.assertEqual(events[0]["request_id"], "abc-123")
        self.assertEqual(events[0]["v"], 1)

    def test_omits_request_id_when_none(self):
        handler = FakeHandler()
        send_sse_event(handler, {"type": "done"})

        events = handler.read_events()
        self.assertNotIn("request_id", events[0])

    def test_omits_request_id_when_empty(self):
        handler = FakeHandler()
        send_sse_event(handler, {"type": "done"}, request_id="")

        events = handler.read_events()
        self.assertNotIn("request_id", events[0])

    def test_does_not_mutate_original_payload(self):
        handler = FakeHandler()
        payload = {"type": "token", "content": "x"}
        send_sse_event(handler, payload, request_id="r1")

        self.assertNotIn("v", payload)
        self.assertNotIn("request_id", payload)

    def test_multiple_events_each_enriched(self):
        handler = FakeHandler()
        send_sse_event(handler, {"type": "search_start"}, request_id="r1")
        send_sse_event(handler, {"type": "search_done", "results": []}, request_id="r1")
        send_sse_event(handler, {"type": "done"}, request_id="r1")

        events = handler.read_events()
        self.assertEqual(len(events), 3)
        for evt in events:
            self.assertEqual(evt["v"], 1)
            self.assertEqual(evt["request_id"], "r1")




    class headers(dict):  # noqa: N801
        """dict that also supports .get()"""

    def __init_subclass__(cls) -> None: ...


class _SimpleHandler:
    def __init__(self, body: bytes, content_length: str | None = None):
        self.rfile = io.BytesIO(body)
        cl = content_length if content_length is not None else str(len(body))
        self._headers = {"Content-Length": cl}

    @property
    def headers(self):
        return self._headers


class TestReadJsonBody(unittest.TestCase):
    def test_normal_payload(self):
        body = json.dumps({"message": "hi"}).encode()
        handler = _SimpleHandler(body)
        result = read_json_body(handler)
        self.assertEqual(result, {"message": "hi"})

    def test_oversized_payload_raises_payload_too_large(self):
        handler = _SimpleHandler(b"x", content_length="99999999999")
        with self.assertRaises(PayloadTooLargeError):
            read_json_body(handler)

    def test_negative_content_length_reads_nothing(self):
        handler = _SimpleHandler(b'{"a":1}', content_length="-5")
        with self.assertRaises(json.JSONDecodeError):
            read_json_body(handler)

    def test_non_numeric_content_length_reads_nothing(self):
        handler = _SimpleHandler(b'{"a":1}', content_length="abc")
        with self.assertRaises(json.JSONDecodeError):
            read_json_body(handler)

    def test_missing_content_length_reads_nothing(self):
        handler = _SimpleHandler(b'{"a":1}', content_length="0")
        with self.assertRaises(json.JSONDecodeError):
            read_json_body(handler)


class _StaticHandler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self._status = None
        self._headers = {}

    def send_response(self, status):
        self._status = status

    def send_header(self, key, value):
        self._headers[key] = value

    def end_headers(self):
        pass


class TestServeStatic(unittest.TestCase):
    def test_path_traversal_returns_403(self):
        handler = _StaticHandler()
        frontend_dir = Path(__file__).parent
        with patch("backend.http_utils.send_json") as send_json_mock:
            serve_static(handler, frontend_dir, "../../etc/passwd")
        send_json_mock.assert_called_once()
        self.assertEqual(send_json_mock.call_args[0][1], 403)

    def test_error_response_has_no_detail(self):
        handler = _StaticHandler()
        frontend_dir = Path(__file__).parent / "nonexistent_dir_xyz"
        with patch("backend.http_utils.send_json") as send_json_mock:
            serve_static(handler, frontend_dir, "file.txt")
        if send_json_mock.called:
            payload = send_json_mock.call_args[0][2]
            self.assertNotIn("detail", payload)


if __name__ == "__main__":
    unittest.main()

import io
import json
import unittest

from backend.http_utils import send_sse_event


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


if __name__ == "__main__":
    unittest.main()

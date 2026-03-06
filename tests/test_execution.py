import unittest

from backend.domain.execution import CancellationRegistry, CancellationToken, EventSink, SseEventStream


class TestExecutionPrimitives(unittest.TestCase):
    def test_finish_only_removes_matching_token_for_same_request_id(self):
        registry = CancellationRegistry()
        first = registry.register("rid-1")
        second = registry.register("rid-1")

        registry.finish("rid-1", first)

        self.assertIs(registry.get("rid-1"), second)
        self.assertTrue(registry.cancel("rid-1"))

    def test_finish_removes_matching_token(self):
        registry = CancellationRegistry()
        token = registry.register("rid-2")

        registry.finish("rid-2", token)

        self.assertIsNone(registry.get("rid-2"))

    def test_terminal_done_event_survives_after_cancellation(self):
        token = CancellationToken()
        sink = EventSink(cancel_token=token)

        token.cancel()
        sink.emit({"type": "token", "content": "ignored"})
        sink.emit({"type": "done", "finish_reason": "stop"})
        sink.close()

        events = list(sink.iter_events())
        self.assertEqual(events, [{"type": "done", "finish_reason": "stop"}])

    def test_sse_stream_does_not_duplicate_done_when_sink_emits_terminal_event(self):
        token = CancellationToken()
        sink = EventSink(cancel_token=token)
        stream = SseEventStream(sink, cancel_token=token)

        token.cancel()
        sink.emit({"type": "done", "finish_reason": "stop"})
        sink.close()

        events = list(stream.iter_events())
        self.assertEqual(events, [{"type": "done", "finish_reason": "stop"}])

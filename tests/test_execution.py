import unittest
from threading import Thread
from time import sleep

from backend.domain.execution import (
    CancellationRegistry,
    CancellationToken,
    DuplicateRequestIdError,
    EventSink,
    SseEventStream,
)


class TestExecutionPrimitives(unittest.TestCase):
    def test_finish_only_removes_matching_active_token(self):
        registry = CancellationRegistry()
        active = registry.register("rid-1", kind="stream")
        stale = CancellationToken()

        registry.finish("rid-1", stale)

        self.assertIs(registry.get("rid-1"), active)
        self.assertTrue(registry.cancel("rid-1"))

    def test_finish_removes_matching_token(self):
        registry = CancellationRegistry()
        token = registry.register("rid-2", kind="stream")

        registry.finish("rid-2", token)

        self.assertIsNone(registry.get("rid-2"))

    def test_cancel_active_streams_only_cancels_stream_entries(self):
        registry = CancellationRegistry()
        stream_token = registry.register("rid-stream", kind="stream")
        once_token = registry.register("rid-once", kind="once")

        cancelled = registry.cancel_active_streams()

        self.assertEqual(cancelled, 1)
        self.assertTrue(stream_token.cancelled)
        self.assertFalse(once_token.cancelled)

    def test_wait_for_no_active_streams_succeeds_after_stream_finishes(self):
        registry = CancellationRegistry()
        token = registry.register("rid-stream", kind="stream")

        def finish_later():
            sleep(0.05)
            registry.finish("rid-stream", token)

        worker = Thread(target=finish_later, daemon=True)
        worker.start()

        self.assertTrue(registry.wait_for_no_active_streams(0.5))

    def test_wait_for_no_active_streams_times_out_while_stream_is_active(self):
        registry = CancellationRegistry()
        registry.register("rid-stream", kind="stream")

        self.assertFalse(registry.wait_for_no_active_streams(0.01))

    def test_register_rejects_duplicate_active_request_id(self):
        registry = CancellationRegistry()
        registry.register("rid-dup", kind="stream")

        with self.assertRaises(DuplicateRequestIdError):
            registry.register("rid-dup", kind="once")

    def test_register_allows_reuse_after_finish(self):
        registry = CancellationRegistry()
        token = registry.register("rid-reuse", kind="stream")

        registry.finish("rid-reuse", token)

        reused = registry.register("rid-reuse", kind="once")
        self.assertIsNotNone(reused)

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

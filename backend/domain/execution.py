from __future__ import annotations

import queue
import threading
from dataclasses import dataclass


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class CancellationRegistry:
    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = threading.Lock()

    def register(self, request_id: str, token: CancellationToken | None = None) -> CancellationToken:
        with self._lock:
            created = token or CancellationToken()
            self._tokens[request_id] = created
            return created

    def get(self, request_id: str) -> CancellationToken | None:
        with self._lock:
            return self._tokens.get(request_id)

    def cancel(self, request_id: str) -> bool:
        token = self.get(request_id)
        if token is None:
            return False
        token.cancel()
        return True

    def finish(self, request_id: str, token: CancellationToken) -> None:
        with self._lock:
            current = self._tokens.get(request_id)
            if current is token:
                self._tokens.pop(request_id, None)


@dataclass(frozen=True)
class ChatExecutionContext:
    request_id: str
    resolved_model: str
    provider: str
    protocol: str
    thinking_mode: bool
    agent_mode: bool | None
    enable_search: bool
    cancel_token: CancellationToken
    debug_stream: bool = False


class EventSink:
    def __init__(self, cancel_token: CancellationToken | None = None) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._closed = threading.Event()
        self._cancel_token = cancel_token

    @staticmethod
    def _is_terminal_event(event: dict) -> bool:
        return event.get("type") == "done"

    def emit(self, event: dict) -> None:
        if self._closed.is_set():
            return
        if self._cancel_token and self._cancel_token.cancelled and not self._is_terminal_event(event):
            return
        self._queue.put(event)

    def close(self) -> None:
        self._closed.set()

    def iter_events(self, poll_seconds: float = 0.1):
        while not self._closed.is_set() or not self._queue.empty():
            if self._cancel_token and self._cancel_token.cancelled and self._queue.empty():
                break
            try:
                yield self._queue.get(timeout=poll_seconds)
            except queue.Empty:
                continue


class SseEventStream:
    def __init__(self, sink: EventSink, cancel_token: CancellationToken | None = None) -> None:
        self._sink = sink
        self._cancel_token = cancel_token

    def iter_events(self):
        terminal_sent = False
        for event in self._sink.iter_events():
            if event.get("type") == "done":
                terminal_sent = True
            yield event
        if self._cancel_token and self._cancel_token.cancelled and not terminal_sent:
            yield {"type": "done", "finish_reason": "stop"}

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Literal


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


ExecutionKind = Literal["stream", "once"]


@dataclass(frozen=True)
class RegisteredExecution:
    request_id: str
    kind: ExecutionKind
    token: CancellationToken


class DuplicateRequestIdError(RuntimeError):
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__("request_id already active")


class CancellationRegistry:
    def __init__(self) -> None:
        self._executions: dict[str, RegisteredExecution] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def register(
        self,
        request_id: str,
        *,
        kind: ExecutionKind = "stream",
        token: CancellationToken | None = None,
    ) -> CancellationToken:
        with self._condition:
            if request_id in self._executions:
                raise DuplicateRequestIdError(request_id)
            created = token or CancellationToken()
            self._executions[request_id] = RegisteredExecution(
                request_id=request_id,
                kind=kind,
                token=created,
            )
            self._condition.notify_all()
            return created

    def get(self, request_id: str) -> CancellationToken | None:
        with self._condition:
            entry = self._executions.get(request_id)
            return entry.token if entry is not None else None

    def cancel(self, request_id: str) -> bool:
        token = self.get(request_id)
        if token is None:
            return False
        token.cancel()
        return True

    def active_stream_count(self) -> int:
        with self._condition:
            return sum(1 for entry in self._executions.values() if entry.kind == "stream")

    def cancel_active_streams(self) -> int:
        with self._condition:
            stream_tokens = [entry.token for entry in self._executions.values() if entry.kind == "stream"]
        for token in stream_tokens:
            token.cancel()
        return len(stream_tokens)

    def wait_for_no_active_streams(self, timeout: float) -> bool:
        timeout_s = max(0.0, float(timeout))
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while any(entry.kind == "stream" for entry in self._executions.values()):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def finish(self, request_id: str, token: CancellationToken) -> None:
        with self._condition:
            current = self._executions.get(request_id)
            if current is not None and current.token is token:
                self._executions.pop(request_id, None)
                self._condition.notify_all()


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

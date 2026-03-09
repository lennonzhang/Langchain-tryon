from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager


class QueueFullError(RuntimeError):
    pass


class QueueTimeoutError(RuntimeError):
    pass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.1, float(raw))
    except ValueError:
        return default


class AdmissionGate:
    def __init__(
        self,
        *,
        max_concurrency: int,
        max_queue_size: int,
        queue_timeout_seconds: float,
    ) -> None:
        self._max_concurrency = max(1, max_concurrency)
        self._max_queue_size = max(0, max_queue_size)
        self._queue_timeout_seconds = max(0.1, queue_timeout_seconds)
        self._active = 0
        self._waiting = 0
        self._condition = asyncio.Condition()

    @classmethod
    def from_env(cls) -> "AdmissionGate":
        return cls(
            max_concurrency=_int_env("GATEWAY_MAX_CONCURRENCY", 16),
            max_queue_size=max(0, _int_env("GATEWAY_MAX_QUEUE_SIZE", 64)),
            queue_timeout_seconds=_float_env("GATEWAY_QUEUE_TIMEOUT_SECONDS", 15.0),
        )

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._condition:
            if self._active < self._max_concurrency:
                self._active += 1
                return
            if self._waiting >= self._max_queue_size:
                raise QueueFullError("gateway queue is full")
            self._waiting += 1
            try:
                deadline = loop.time() + self._queue_timeout_seconds
                while self._active >= self._max_concurrency:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise QueueTimeoutError("gateway queue timeout")
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                    except asyncio.TimeoutError as exc:
                        raise QueueTimeoutError("gateway queue timeout") from exc
                self._active += 1
            finally:
                self._waiting -= 1

    async def release(self) -> None:
        async with self._condition:
            if self._active > 0:
                self._active -= 1
            self._condition.notify(1)

    @asynccontextmanager
    async def slot(self):
        await self.acquire()
        try:
            yield
        finally:
            await self.release()


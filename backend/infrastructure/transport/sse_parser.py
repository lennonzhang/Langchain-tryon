from __future__ import annotations

from typing import Any, Iterator


def iter_sse_events(resp) -> Iterator[dict[str, Any]]:
    event_name = ""
    data_parts: list[str] = []
    line_count = 0

    def flush():
        nonlocal event_name, data_parts
        if not event_name and not data_parts:
            return None
        data_raw = "\n".join(data_parts).strip()
        item = {"event": event_name or "message", "data": data_raw, "line_count": line_count}
        event_name = ""
        data_parts = []
        return item

    for raw_line in resp:
        line_count += 1
        line = raw_line.decode("utf-8", errors="ignore").rstrip("\r\n")
        if not line.strip():
            item = flush()
            if item is not None:
                yield item
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            if data_parts and not event_name:
                item = flush()
                if item is not None:
                    yield item
            data_parts.append(line[5:].lstrip())
    item = flush()
    if item is not None:
        yield item

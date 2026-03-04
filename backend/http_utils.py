from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_JSON_BODY = 10 * 1024 * 1024  # 10 MB


class PayloadTooLargeError(ValueError):
    """Raised when the request body exceeds ``_MAX_JSON_BODY``."""


def send_json(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler) -> dict:
    try:
        content_length = int(handler.headers.get("Content-Length", "0"))
    except (ValueError, TypeError):
        content_length = 0
    if content_length < 0:
        content_length = 0
    if content_length > _MAX_JSON_BODY:
        raise PayloadTooLargeError(
            f"Payload too large ({content_length} bytes, max {_MAX_JSON_BODY})"
        )
    raw = handler.rfile.read(content_length)
    return json.loads(raw.decode("utf-8"))


def init_sse(handler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()


def send_sse_event(handler, payload: dict, *, request_id: str | None = None) -> None:
    enriched = {**payload, "v": 1}
    if request_id:
        enriched["request_id"] = request_id
    body = json.dumps(enriched, ensure_ascii=False)
    handler.wfile.write(f"data: {body}\n\n".encode("utf-8"))
    handler.wfile.flush()


def serve_static(handler, frontend_dir: Path, rel_path: str) -> None:
    if rel_path in {"", "/"}:
        target = frontend_dir / "index.html"
    else:
        safe_rel = rel_path.lstrip("/")
        target = frontend_dir / safe_rel

    try:
        target = target.resolve()
        try:
            target.relative_to(frontend_dir.resolve())
        except ValueError:
            send_json(handler, 403, {"error": "Forbidden"})
            return
        if not target.exists() or not target.is_file():
            send_json(handler, 404, {"error": "Not found"})
            return

        body = target.read_bytes()
        content_type, _ = mimetypes.guess_type(str(target))
        handler.send_response(200)
        handler.send_header("Content-Type", f"{content_type or 'application/octet-stream'}")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to serve static file: %s", rel_path)
        send_json(handler, 500, {"error": "Failed to serve file"})


import json
import mimetypes
from pathlib import Path


def send_json(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler) -> dict:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length)
    return json.loads(raw.decode("utf-8"))


def init_sse(handler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()


def send_sse_event(handler, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False)
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
        if not str(target).startswith(str(frontend_dir.resolve())):
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
    except Exception as exc:  # noqa: BLE001
        send_json(handler, 500, {"error": "Failed to serve file", "detail": str(exc)})


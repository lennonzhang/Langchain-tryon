import json
from urllib import error

from .http_utils import init_sse, read_json_body, send_json, send_sse_event
from .nvidia_client import chat_once, stream_chat


def handle_chat_once(handler, api_key: str) -> None:
    try:
        data = read_json_body(handler)
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])
    model = data.get("model")
    enable_search = bool(data.get("web_search", False))
    if not message:
        send_json(handler, 400, {"error": "message is required"})
        return

    try:
        answer = chat_once(api_key, message, history, model, enable_search=enable_search)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        send_json(handler, 502, {"error": "Upstream HTTP error", "detail": detail[:500]})
        return
    except Exception as exc:  # noqa: BLE001
        send_json(handler, 502, {"error": "Upstream request failed", "detail": str(exc)})
        return

    send_json(handler, 200, {"answer": answer})


def handle_chat_stream(handler, api_key: str) -> None:
    try:
        data = read_json_body(handler)
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    message = str(data.get("message", "")).strip()
    history = data.get("history", [])
    model = data.get("model")
    enable_search = bool(data.get("web_search", False))
    if not message:
        send_json(handler, 400, {"error": "message is required"})
        return

    init_sse(handler)

    try:
        for event in stream_chat(api_key, message, history, model, enable_search=enable_search):
            send_sse_event(handler, event)
    except Exception as exc:  # noqa: BLE001
        try:
            send_sse_event(handler, {"type": "error", "error": str(exc)})
        except OSError:
            # Client disconnected; nothing left to write.
            return
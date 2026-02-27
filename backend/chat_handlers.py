import json
from urllib import error

from .http_utils import init_sse, read_json_body, send_json, send_sse_event
from .nvidia_client import chat_once, stream_chat


def _is_gateway_timeout_error(exc: Exception) -> bool:
    detail = str(exc)
    return "504" in detail and "Gateway Timeout" in detail


def _parse_chat_payload(data: dict) -> dict:
    agent_mode = data.get("agent_mode", None)
    if not isinstance(agent_mode, bool):
        agent_mode = None

    return {
        "message": str(data.get("message", "")).strip(),
        "history": data.get("history", []),
        "model": data.get("model"),
        "enable_search": bool(data.get("web_search", False)),
        "agent_mode": agent_mode,
        "thinking_mode": bool(data.get("thinking_mode", True)),
        "images": data.get("images", []),
    }


def handle_chat_once(handler, api_key: str) -> None:
    try:
        data = read_json_body(handler)
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    payload = _parse_chat_payload(data)
    message = payload["message"]
    if not message:
        send_json(handler, 400, {"error": "message is required"})
        return

    try:
        answer = chat_once(
            api_key,
            message,
            payload["history"],
            payload["model"],
            enable_search=payload["enable_search"],
            agent_mode=payload["agent_mode"],
            thinking_mode=payload["thinking_mode"],
            images=payload["images"],
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        send_json(handler, 502, {"error": "Upstream HTTP error", "detail": detail[:500]})
        return
    except TimeoutError as exc:
        send_json(
            handler,
            504,
            {"error": "Upstream request timeout", "detail": str(exc)[:500]},
        )
        return
    except Exception as exc:  # noqa: BLE001
        if _is_gateway_timeout_error(exc):
            send_json(
                handler,
                504,
                {"error": "Upstream gateway timeout", "detail": str(exc)[:500]},
            )
            return
        send_json(handler, 502, {"error": "Upstream request failed", "detail": str(exc)})
        return

    send_json(handler, 200, {"answer": answer})


def handle_chat_stream(handler, api_key: str) -> None:
    try:
        data = read_json_body(handler)
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    payload = _parse_chat_payload(data)
    message = payload["message"]
    if not message:
        send_json(handler, 400, {"error": "message is required"})
        return

    init_sse(handler)

    try:
        for event in stream_chat(
            api_key,
            message,
            payload["history"],
            payload["model"],
            enable_search=payload["enable_search"],
            agent_mode=payload["agent_mode"],
            thinking_mode=payload["thinking_mode"],
            images=payload["images"],
        ):
            send_sse_event(handler, event)
    except TimeoutError as exc:
        try:
            send_sse_event(
                handler,
                {"type": "error", "error": f"Upstream request timeout: {str(exc)[:500]}"},
            )
        except OSError:
            return
    except Exception as exc:  # noqa: BLE001
        if _is_gateway_timeout_error(exc):
            try:
                send_sse_event(handler, {"type": "error", "error": "Upstream gateway timeout"})
            except OSError:
                return
            return
        try:
            send_sse_event(handler, {"type": "error", "error": str(exc)})
        except OSError:
            # Client disconnected; nothing left to write.
            return

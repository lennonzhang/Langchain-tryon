from __future__ import annotations

import json
from urllib import error

from .http_utils import init_sse, read_json_body, send_json, send_sse_event
from .nvidia_client import chat_once, stream_chat
from .schemas import ChatRequest


def _is_gateway_timeout_error(exc: Exception) -> bool:
    detail = str(exc)
    return "504" in detail and "Gateway Timeout" in detail


def handle_chat_once(handler, api_key: str) -> None:
    try:
        data = read_json_body(handler)
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    req = ChatRequest.from_dict(data)
    if not req.message:
        send_json(handler, 400, {"error": "message is required"})
        return

    try:
        answer = chat_once(
            api_key,
            req.message,
            req.history,
            req.model,
            enable_search=req.enable_search,
            agent_mode=req.agent_mode,
            thinking_mode=req.thinking_mode,
            images=req.images,
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

    req = ChatRequest.from_dict(data)
    if not req.message:
        send_json(handler, 400, {"error": "message is required"})
        return

    rid = req.request_id
    init_sse(handler)

    def _emit(payload: dict) -> None:
        send_sse_event(handler, payload, request_id=rid)

    def _emit_error_and_done(error_msg: str) -> None:
        try:
            _emit({"type": "error", "error": error_msg})
            _emit({"type": "done", "finish_reason": "error"})
        except OSError:
            return

    try:
        for event in stream_chat(
            api_key,
            req.message,
            req.history,
            req.model,
            enable_search=req.enable_search,
            agent_mode=req.agent_mode,
            thinking_mode=req.thinking_mode,
            images=req.images,
        ):
            _emit(event)
    except TimeoutError as exc:
        _emit_error_and_done(f"Upstream request timeout: {str(exc)[:500]}")
    except Exception as exc:  # noqa: BLE001
        if _is_gateway_timeout_error(exc):
            _emit_error_and_done("Upstream gateway timeout")
            return
        _emit_error_and_done(str(exc))

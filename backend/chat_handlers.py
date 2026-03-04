from __future__ import annotations

import json
import logging
from urllib import error

from .config import resolve_model
from .http_utils import PayloadTooLargeError, init_sse, read_json_body, send_json, send_sse_event
from .nvidia_client import chat_once, stream_chat
from .provider_event_normalizer import normalize_upstream_error, normalized_error_detail
from .schemas import ChatRequest, ValidationError

logger = logging.getLogger(__name__)
_PREVIEW_LIMIT = 80


def _is_gateway_timeout_error(exc: Exception) -> bool:
    detail = str(exc)
    return "504" in detail and "Gateway Timeout" in detail


def _single_line_preview(value, limit: int = _PREVIEW_LIMIT) -> str:
    text = str(value or "")
    collapsed = " ".join(text.split())
    return collapsed[:limit]


def _debug_log(enabled: bool, rid: str, model: str, evt: str, **fields) -> None:
    if not enabled:
        return
    parts = [f"rid={rid}", f"model={model}", f"evt={evt}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    logger.info("[stream-debug] %s", " ".join(parts))


def _debug_log_stream_event(enabled: bool, rid: str, model: str, event: dict) -> None:
    if not enabled:
        return
    evt = event.get("type", "unknown")
    if evt in {"token", "reasoning"}:
        content = event.get("content", "")
        _debug_log(
            True,
            rid,
            model,
            evt,
            len=len(str(content)),
            preview=f'"{_single_line_preview(content)}"',
        )
        return
    if evt == "search_done":
        results = event.get("results", [])
        count = len(results) if isinstance(results, list) else "?"
        _debug_log(True, rid, model, evt, results=count)
        return
    if evt == "context_usage":
        usage = event.get("usage", {})
        ratio = usage.get("usage_ratio") if isinstance(usage, dict) else None
        _debug_log(True, rid, model, evt, usage_ratio=ratio)
        return
    if evt == "error":
        _debug_log(
            True,
            rid,
            model,
            evt,
            preview=f'"{_single_line_preview(event.get("error", ""))}"',
        )
        return
    if evt == "done":
        _debug_log(True, rid, model, evt, finish_reason=event.get("finish_reason"))
        return
    if evt in {"tool_call", "tool_result"}:
        _debug_log(True, rid, model, evt, tool=event.get("tool"), step=event.get("step"))
        return
    _debug_log(True, rid, model, evt)


def handle_chat_once(handler, api_key: str, debug_stream: bool = False) -> None:
    try:
        data = read_json_body(handler)
    except PayloadTooLargeError:
        send_json(handler, 413, {"error": "Payload too large"})
        return
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    try:
        req = ChatRequest.from_dict(data)
    except ValidationError as ve:
        send_json(handler, 400, {"error": str(ve)})
        return
    if not req.message:
        send_json(handler, 400, {"error": "message is required"})
        return
    resolved_model = resolve_model(req.model)
    _debug_log(
        debug_stream,
        req.request_id,
        resolved_model,
        "chat_once_start",
        agent_mode=req.agent_mode,
        thinking=req.thinking_mode,
        web_search=req.enable_search,
    )

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
        info = normalize_upstream_error(
            resolved_model,
            status=getattr(exc, "code", None),
            raw_body=detail,
        )
        _debug_log(
            debug_stream,
            req.request_id,
            resolved_model,
            "chat_once_error",
            error_type="http_error",
            preview=f'"{_single_line_preview(normalized_error_detail(info))}"',
        )
        send_json(
            handler,
            502,
            {"error": "Upstream HTTP error", "detail": normalized_error_detail(info)[:500]},
        )
        return
    except TimeoutError as exc:
        _debug_log(
            debug_stream,
            req.request_id,
            resolved_model,
            "chat_once_error",
            error_type="timeout",
            preview=f'"{_single_line_preview(exc)}"',
        )
        send_json(
            handler,
            504,
            {"error": "Upstream request timeout", "detail": str(exc)[:500]},
        )
        return
    except Exception as exc:  # noqa: BLE001
        _debug_log(
            debug_stream,
            req.request_id,
            resolved_model,
            "chat_once_error",
            error_type=type(exc).__name__,
            preview=f'"{_single_line_preview(exc)}"',
        )
        if _is_gateway_timeout_error(exc):
            send_json(
                handler,
                504,
                {"error": "Upstream gateway timeout", "detail": str(exc)[:500]},
            )
            return
        info = normalize_upstream_error(
            resolved_model,
            raw_body=str(exc),
        )
        send_json(
            handler,
            502,
            {"error": "Upstream request failed", "detail": normalized_error_detail(info)[:500]},
        )
        return

    _debug_log(
        debug_stream,
        req.request_id,
        resolved_model,
        "chat_once_done",
        answer_len=len(answer),
    )
    send_json(handler, 200, {"answer": answer})


def handle_chat_stream(handler, api_key: str, debug_stream: bool = False) -> None:
    try:
        data = read_json_body(handler)
    except PayloadTooLargeError:
        send_json(handler, 413, {"error": "Payload too large"})
        return
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    try:
        req = ChatRequest.from_dict(data)
    except ValidationError as ve:
        send_json(handler, 400, {"error": str(ve)})
        return
    if not req.message:
        send_json(handler, 400, {"error": "message is required"})
        return

    rid = req.request_id
    resolved_model = resolve_model(req.model)
    _debug_log(
        debug_stream,
        rid,
        resolved_model,
        "stream_start",
        agent_mode=req.agent_mode,
        thinking=req.thinking_mode,
        web_search=req.enable_search,
    )
    init_sse(handler)

    def _emit(payload: dict) -> None:
        send_sse_event(handler, payload, request_id=rid)

    def _emit_error_and_done(error_msg: str) -> None:
        try:
            _debug_log(
                debug_stream,
                rid,
                resolved_model,
                "error",
                preview=f'"{_single_line_preview(error_msg)}"',
            )
            _emit({"type": "error", "error": error_msg})
            _debug_log(debug_stream, rid, resolved_model, "done", finish_reason="error")
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
            _debug_log_stream_event(debug_stream, rid, resolved_model, event)
            _emit(event)
    except TimeoutError as exc:
        _debug_log(
            debug_stream,
            rid,
            resolved_model,
            "stream_exception",
            error_type="timeout",
            preview=f'"{_single_line_preview(exc)}"',
        )
        _emit_error_and_done(f"Upstream request timeout: {str(exc)[:500]}")
    except Exception as exc:  # noqa: BLE001
        _debug_log(
            debug_stream,
            rid,
            resolved_model,
            "stream_exception",
            error_type=type(exc).__name__,
            preview=f'"{_single_line_preview(exc)}"',
        )
        if _is_gateway_timeout_error(exc):
            _emit_error_and_done("Upstream gateway timeout")
            return
        info = normalize_upstream_error(
            resolved_model,
            raw_body=str(exc),
        )
        _emit_error_and_done(normalized_error_detail(info))

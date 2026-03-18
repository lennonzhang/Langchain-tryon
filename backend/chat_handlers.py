from __future__ import annotations

import json
import logging
from urllib import error

from .chat_logger import log_llm_error, log_request_lifecycle, log_sse_event
from .config import resolve_model
from .http_utils import PayloadTooLargeError, init_sse, read_json_body, send_json, send_sse_event
from .nvidia_client import cancel_chat, chat_once, stream_chat
from .provider_event_normalizer import normalize_upstream_error, normalized_error_detail
from .schemas import ChatRequest, ValidationError

logger = logging.getLogger(__name__)


def _is_gateway_timeout_error(exc: Exception) -> bool:
    detail = str(exc)
    return "504" in detail and "Gateway Timeout" in detail


def _single_line_preview(value, limit: int = 80) -> str:
    text = str(value or "")
    collapsed = " ".join(text.split())
    return collapsed[:limit]


def handle_chat_once(handler, api_key: str) -> None:
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
    log_request_lifecycle(
        rid=req.request_id, model=resolved_model, evt="chat_once_start",
        agent_mode=req.agent_mode, thinking=req.thinking_mode, web_search=req.enable_search,
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
            request_id=req.request_id,
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        info = normalize_upstream_error(
            resolved_model,
            status=getattr(exc, "code", None),
            raw_body=detail,
        )
        log_llm_error(
            rid=req.request_id, model=resolved_model, provider="",
            error_type="http_error", error_detail=normalized_error_detail(info),
        )
        send_json(
            handler,
            502,
            {"error": "Upstream HTTP error", "detail": normalized_error_detail(info)[:500]},
        )
        return
    except TimeoutError as exc:
        log_llm_error(
            rid=req.request_id, model=resolved_model, provider="",
            error_type="timeout", error_detail=str(exc),
        )
        send_json(
            handler,
            504,
            {"error": "Upstream request timeout", "detail": str(exc)[:500]},
        )
        return
    except Exception as exc:  # noqa: BLE001
        log_llm_error(
            rid=req.request_id, model=resolved_model, provider="",
            error_type=type(exc).__name__, error_detail=str(exc),
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

    log_request_lifecycle(
        rid=req.request_id, model=resolved_model, evt="chat_once_done",
        answer_len=len(answer),
    )
    send_json(handler, 200, {"answer": answer})


def handle_chat_stream(handler, api_key: str) -> None:
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
    log_request_lifecycle(
        rid=rid, model=resolved_model, evt="stream_start",
        agent_mode=req.agent_mode, thinking=req.thinking_mode, web_search=req.enable_search,
    )
    init_sse(handler)

    def _emit(payload: dict) -> None:
        send_sse_event(handler, payload, request_id=rid)

    def _emit_error_and_done(error_msg: str) -> None:
        try:
            log_llm_error(
                rid=rid, model=resolved_model, provider="",
                error_type="stream_error", error_detail=error_msg,
            )
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
            request_id=rid,
        ):
            log_sse_event(rid=rid, model=resolved_model, event=event)
            _emit(event)
    except TimeoutError as exc:
        log_llm_error(
            rid=rid, model=resolved_model, provider="",
            error_type="timeout", error_detail=str(exc),
        )
        _emit_error_and_done(f"Upstream request timeout: {str(exc)[:500]}")
    except Exception as exc:  # noqa: BLE001
        log_llm_error(
            rid=rid, model=resolved_model, provider="",
            error_type=type(exc).__name__, error_detail=str(exc),
        )
        if _is_gateway_timeout_error(exc):
            _emit_error_and_done("Upstream gateway timeout")
            return
        info = normalize_upstream_error(
            resolved_model,
            raw_body=str(exc),
        )
        _emit_error_and_done(normalized_error_detail(info))


def handle_chat_cancel(handler) -> None:
    try:
        data = read_json_body(handler)
    except PayloadTooLargeError:
        send_json(handler, 413, {"error": "Payload too large"})
        return
    except (ValueError, json.JSONDecodeError):
        send_json(handler, 400, {"error": "Invalid JSON body"})
        return

    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        send_json(handler, 400, {"error": "request_id is required"})
        return
    request_id = request_id.strip()
    if len(request_id) > ChatRequest._MAX_REQUEST_ID_CHARS:
        send_json(
            handler,
            400,
            {"error": f"request_id: too long (max {ChatRequest._MAX_REQUEST_ID_CHARS} chars)"},
        )
        return

    send_json(handler, 200, cancel_chat(request_id))

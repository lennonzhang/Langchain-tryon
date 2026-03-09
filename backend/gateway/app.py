from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from backend.config import load_api_key
from backend.model_registry import capabilities_response
from backend.nvidia_client import cancel_chat, chat_once, stream_chat
from backend.schemas import ChatRequest, ValidationError
from backend.gateway.admission import AdmissionGate, QueueFullError, QueueTimeoutError

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"

app = FastAPI()
_ADMISSION_GATE = AdmissionGate.from_env()
app.state.debug_stream = False
_MAX_JSON_BODY = 10 * 1024 * 1024
_MAX_REQUEST_ID_CHARS = ChatRequest._MAX_REQUEST_ID_CHARS


class GatewayRequestError(Exception):
    pass


class PayloadTooLargeError(GatewayRequestError):
    pass


class InvalidJsonBodyError(GatewayRequestError):
    pass


class RequestValidationError(GatewayRequestError):
    pass


class MissingMessageError(GatewayRequestError):
    pass


def _content_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return max(0, value)


def _validate_request_id(value: object, *, required: bool) -> str | None:
    if not isinstance(value, str) or not value.strip():
        if required:
            raise RequestValidationError("request_id is required")
        return None
    request_id = value.strip()
    if len(request_id) > _MAX_REQUEST_ID_CHARS:
        raise RequestValidationError(f"request_id: too long (max {_MAX_REQUEST_ID_CHARS} chars)")
    return request_id


def _json_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


def _configuration_error(message: str) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "Server misconfigured", "detail": message[:500]})


def _enrich_event(payload: dict, request_id: str | None = None) -> str:
    enriched = {**payload, "v": 1}
    if request_id:
        enriched["request_id"] = request_id
    return f"data: {json.dumps(enriched, ensure_ascii=False)}\n\n"


async def _parse_chat_request(request: Request) -> ChatRequest:
    content_length = _content_length(request)
    if content_length is not None and content_length > _MAX_JSON_BODY:
        raise PayloadTooLargeError("Payload too large")
    body = await request.body()
    if len(body) > _MAX_JSON_BODY:
        raise PayloadTooLargeError("Payload too large")
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except Exception as exc:  # noqa: BLE001
        raise InvalidJsonBodyError("Invalid JSON body") from exc
    try:
        req = ChatRequest.from_dict(data)
    except ValidationError as exc:
        raise RequestValidationError(str(exc)) from exc
    if not req.message:
        raise MissingMessageError("message is required")
    return req


@app.get("/api/capabilities")
async def get_capabilities():
    return capabilities_response()


def _stream_error_response(message: str, request_id: str | None) -> StreamingResponse:
    async def generate():
        yield _enrich_event({"type": "error", "error": message}, request_id)
        yield _enrich_event({"type": "done", "finish_reason": "error"}, request_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


def _require_api_key() -> str:
    return load_api_key(BASE_DIR)


def _safe_frontend_target(rel_path: str) -> tuple[Path | None, int | None]:
    frontend_root = FRONTEND_DIST_DIR.resolve()
    if rel_path in {"", "/"}:
        return frontend_root / "index.html", None

    normalized = rel_path.lstrip("/")
    if "." not in Path(normalized).name:
        return frontend_root / "index.html", None

    try:
        target = (frontend_root / normalized).resolve()
        target.relative_to(frontend_root)
    except ValueError:
        return None, 403
    return target, None


@app.post("/api/chat")
async def post_chat(request: Request):
    try:
        req = await _parse_chat_request(request)
    except PayloadTooLargeError:
        return _json_error(413, "Payload too large")
    except InvalidJsonBodyError:
        return _json_error(400, "Invalid JSON body")
    except RequestValidationError as exc:
        return _json_error(400, str(exc))
    except MissingMessageError as exc:
        return _json_error(400, str(exc))

    try:
        api_key = _require_api_key()
    except RuntimeError as exc:
        return _configuration_error(str(exc))

    try:
        async with _ADMISSION_GATE.slot():
            answer = await asyncio.to_thread(
                chat_once,
                api_key,
                req.message,
                req.history,
                req.model,
                enable_search=req.enable_search,
                agent_mode=req.agent_mode,
                thinking_mode=req.thinking_mode,
                images=req.images,
                request_id=req.request_id,
                debug_stream=bool(getattr(app.state, "debug_stream", False)),
            )
    except (QueueFullError, QueueTimeoutError) as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    except TimeoutError as exc:
        return JSONResponse(status_code=504, content={"error": "Upstream request timeout", "detail": str(exc)[:500]})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": "Upstream request failed", "detail": str(exc)[:500]})
    return {"answer": answer}


@app.post("/api/chat/stream")
async def post_chat_stream(request: Request):
    try:
        req = await _parse_chat_request(request)
    except PayloadTooLargeError:
        return _json_error(413, "Payload too large")
    except InvalidJsonBodyError:
        return _json_error(400, "Invalid JSON body")
    except RequestValidationError as exc:
        return _json_error(400, str(exc))
    except MissingMessageError as exc:
        return _json_error(400, str(exc))

    try:
        await _ADMISSION_GATE.acquire()
    except QueueFullError as exc:
        return _stream_error_response(str(exc), req.request_id)
    except QueueTimeoutError as exc:
        return _stream_error_response(str(exc), req.request_id)

    try:
        api_key = _require_api_key()
    except RuntimeError as exc:
        await _ADMISSION_GATE.release()
        return _stream_error_response(f"Server misconfigured: {str(exc)[:500]}", req.request_id)

    def build_stream():
        return stream_chat(
            api_key,
            req.message,
            req.history,
            req.model,
            enable_search=req.enable_search,
            agent_mode=req.agent_mode,
            thinking_mode=req.thinking_mode,
            images=req.images,
            request_id=req.request_id,
            debug_stream=bool(getattr(app.state, "debug_stream", False)),
        )

    async def generate():
        try:
            async for event in iterate_in_threadpool(build_stream()):
                if await request.is_disconnected():
                    cancel_chat(req.request_id)
                    break
                yield _enrich_event(event, request_id=req.request_id)
        except TimeoutError as exc:
            yield _enrich_event({"type": "error", "error": f"Upstream request timeout: {str(exc)[:500]}"}, req.request_id)
            yield _enrich_event({"type": "done", "finish_reason": "error"}, req.request_id)
        except Exception as exc:  # noqa: BLE001
            yield _enrich_event({"type": "error", "error": str(exc)}, req.request_id)
            yield _enrich_event({"type": "done", "finish_reason": "error"}, req.request_id)
        finally:
            await _ADMISSION_GATE.release()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


@app.post("/api/chat/cancel")
async def post_chat_cancel(request: Request):
    content_length = _content_length(request)
    if content_length is not None and content_length > _MAX_JSON_BODY:
        return _json_error(413, "Payload too large")
    try:
        body_bytes = await request.body()
        if len(body_bytes) > _MAX_JSON_BODY:
            return _json_error(413, "Payload too large")
        body = json.loads(body_bytes.decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        return _json_error(400, "Invalid JSON body")
    try:
        request_id = _validate_request_id(body.get("request_id"), required=True)
    except RequestValidationError as exc:
        return _json_error(400, str(exc))
    return cancel_chat(request_id)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    if not FRONTEND_DIST_DIR.exists():
        return _json_error(404, "Not found")

    rel_path = full_path or "index.html"
    target, error_status = _safe_frontend_target(rel_path)
    if error_status is not None:
        return _json_error(error_status, "Forbidden")

    if target is not None and target.exists() and target.is_file():
        return FileResponse(target)

    if "." in Path(rel_path.lstrip("/")).name:
        return _json_error(404, "Not found")

    fallback = FRONTEND_DIST_DIR / "index.html"
    if fallback.exists():
        return FileResponse(fallback)
    return _json_error(404, "Not found")

"""Normalize provider payloads and errors into backend-friendly shapes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .model_registry import get_protocol, get_provider


@dataclass
class UpstreamErrorInfo:
    provider: str
    protocol: str
    status: int | None
    upstream_error_type: str
    message: str
    request_id: str | None
    raw_body: str


def parse_error_payload(payload: str) -> tuple[str, str, str | None]:
    """Parse known provider error payloads into ``(type, message, request_id)``."""
    raw = str(payload or "").strip()
    if not raw:
        return ("unknown_error", "empty upstream error body", None)
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return ("unknown_error", raw, None)

    if not isinstance(data, dict):
        return ("unknown_error", raw, None)

    rid = data.get("id")
    error = data.get("error")
    if isinstance(error, dict):
        err_type = str(error.get("type") or "unknown_error")
        message = str(error.get("message") or raw)
        return (err_type, message, str(rid) if isinstance(rid, str) else None)

    message = str(data.get("message") or raw)
    err_type = str(data.get("type") or "unknown_error")
    return (err_type, message, str(rid) if isinstance(rid, str) else None)


def normalize_upstream_error(
    model_id: str,
    *,
    status: int | None = None,
    raw_body: str = "",
) -> UpstreamErrorInfo:
    """Build normalized upstream error details for logging and response detail."""
    err_type, message, request_id = parse_error_payload(raw_body)
    return UpstreamErrorInfo(
        provider=get_provider(model_id),
        protocol=get_protocol(model_id),
        status=status,
        upstream_error_type=err_type,
        message=message,
        request_id=request_id,
        raw_body=raw_body,
    )


def normalized_error_detail(info: UpstreamErrorInfo) -> str:
    """Build compact and stable error detail string for API responses."""
    parts = [
        f"provider={info.provider}",
        f"protocol={info.protocol}",
        f"type={info.upstream_error_type}",
    ]
    if info.status is not None:
        parts.append(f"status={info.status}")
    if info.request_id:
        parts.append(f"upstream_request_id={info.request_id}")
    parts.append(f"message={info.message}")
    return " | ".join(parts)

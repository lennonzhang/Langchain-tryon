from __future__ import annotations

import json
import ssl
from typing import Any
from urllib import error, request

from backend.provider_event_normalizer import normalize_upstream_error, normalized_error_detail

_ERROR_PREVIEW_LIMIT = 200


def make_ssl_context(verify: bool = True) -> ssl.SSLContext | None:
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def urlopen(req, timeout: float, ssl_verify: bool = True):
    ctx = make_ssl_context(ssl_verify)
    if ctx is not None:
        return request.urlopen(req, timeout=timeout, context=ctx)
    return request.urlopen(req, timeout=timeout)


def json_post(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_s: float,
    model_id: str = "",
    ssl_verify: bool = True,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(req, timeout_s, ssl_verify=ssl_verify) as resp:
            raw_bytes = resp.read()
            raw_text = raw_bytes.decode("utf-8", errors="ignore")
            if not raw_text.strip():
                raise RuntimeError("empty upstream body")
            try:
                parsed = json.loads(raw_text)
            except Exception as parse_exc:  # noqa: BLE001
                preview = raw_text[:_ERROR_PREVIEW_LIMIT]
                raise RuntimeError(f"non-json upstream body: {preview}") from parse_exc
            if not isinstance(parsed, dict):
                raise RuntimeError(f"non-json upstream body: {str(parsed)[:_ERROR_PREVIEW_LIMIT]}")
            return parsed
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        if model_id:
            info = normalize_upstream_error(model_id, status=getattr(exc, "code", None), raw_body=raw)
            raise RuntimeError(normalized_error_detail(info)) from exc
        raise RuntimeError(raw) from exc

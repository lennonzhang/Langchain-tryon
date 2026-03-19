"""Unified chat lifecycle logging.

Replaces the old ``debug_stream`` / ``_debug_log`` mechanism with a single
logger controlled by ``CHAT_LOG_LEVEL`` (env-var or CLI).

Log events
----------
- ``[llm_send]``   INFO   — outbound LLM request (with message content)
- ``[llm_recv]``   INFO   — inbound LLM response (with response content)
- ``[tool_call]``  INFO   — agent tool invocation (with args)
- ``[tool_result]``INFO   — tool return value (with output)
- ``[llm_error]``  WARNING — LLM call failure
- ``[sse_event]``  DEBUG  — SSE event emitted to frontend
- ``[lifecycle]``  DEBUG  — request-level lifecycle (start / done / cancel)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

_LOGGER_NAME = "backend.chat_lifecycle"
logger = logging.getLogger(_LOGGER_NAME)

_LOG_DIR = "logs"
_LOG_FILE = "latest.log"

_CONTENT_LIMIT = 500
_REASONING_LIMIT = 300
_TOOL_ARGS_LIMIT = 500
_TOOL_OUTPUT_LIMIT = 800
_PREVIEW_LIMIT = 80

_SENSITIVE_KEYS = frozenset({"api_key", "authorization", "token", "secret", "password"})
_DATA_URL_RE = re.compile(r"data:(image|video)/[^;]+;base64,[A-Za-z0-9+/=]{20,}")


# ── configuration ────────────────────────────────────────────────

def configure_chat_logging(cli_level: str | None = None) -> None:
    """Set up the chat lifecycle logger.

    Priority: *cli_level* > ``CHAT_LOG_LEVEL`` env > ``LOG_LEVEL`` env > WARNING.
    """
    level_name = (cli_level or "").strip().upper()
    if not level_name:
        level_name = os.getenv("CHAT_LOG_LEVEL", "").strip().upper()
    if not level_name:
        level_name = os.getenv("LOG_LEVEL", "WARNING").strip().upper()
    level = getattr(logging, level_name, logging.WARNING)
    logger.setLevel(level)


def attach_file_handler(base_dir: Path | None = None) -> None:
    """Add a FileHandler that writes to ``logs/latest.log`` (overwritten each run).

    Call from ``server.py`` only — not at module level — so Vercel
    serverless deploys never trigger file I/O.
    """
    root = base_dir or Path(__file__).resolve().parents[1]
    log_dir = root / _LOG_DIR
    log_dir.mkdir(exist_ok=True)
    log_path = (log_dir / _LOG_FILE).resolve()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for existing in logger.handlers:
        if not isinstance(existing, logging.FileHandler):
            continue
        if Path(getattr(existing, "baseFilename", "")).resolve() != log_path:
            continue
        existing.setFormatter(formatter)
        existing.setLevel(logger.level)
        return

    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(formatter)
    handler.setLevel(logger.level)
    logger.addHandler(handler)
    logger.warning(
        "[lifecycle] log file ready → %s (level=%s)",
        log_path, logging.getLevelName(logger.level),
    )


# ── helpers ──────────────────────────────────────────────────────

def _truncate(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _preview(value: Any, limit: int = _PREVIEW_LIMIT) -> str:
    text = str(value or "")
    collapsed = " ".join(text.split())
    return collapsed[:limit]


def _mask_sensitive(fields: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in fields.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _kv(**fields: Any) -> str:
    safe = _mask_sensitive(fields)
    parts = []
    for key, value in safe.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)


def _format_media_content(content: Any) -> str:
    """Replace base64 data URLs with placeholders."""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                ctype = item.get("type", "")
                if ctype == "text":
                    parts.append(str(item.get("text", "")))
                elif ctype in ("image_url", "video_url"):
                    parts.append(f"[{ctype.split('_')[0]}]")
                else:
                    parts.append(f"[{ctype}]")
            else:
                parts.append(str(item))
        return " ".join(parts)
    text = str(content or "")
    return _DATA_URL_RE.sub("[media]", text)


def _extract_message_role(msg: Any) -> str:
    if hasattr(msg, "type"):
        return str(msg.type)
    if isinstance(msg, dict):
        return str(msg.get("role", "unknown"))
    return type(msg).__name__


def _extract_message_content(msg: Any) -> str:
    if hasattr(msg, "content"):
        raw = msg.content
    elif isinstance(msg, dict):
        raw = msg.get("content", "")
    else:
        raw = str(msg)
    return _format_media_content(raw)


def _format_messages(messages: list | None) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for i, msg in enumerate(messages):
        role = _extract_message_role(msg)
        content = _truncate(_extract_message_content(msg), _CONTENT_LIMIT)
        lines.append(f"  messages[{i}]: role={role} content=\"{content}\"")
    return "\n".join(lines)


def _extract_response_fields(response: Any) -> dict[str, Any]:
    """Extract content, reasoning, and tool_calls from a LangChain response."""
    fields: dict[str, Any] = {}

    # Text content
    content = ""
    if hasattr(response, "content"):
        content = _format_media_content(response.content)
    fields["content"] = content

    # Reasoning
    additional = getattr(response, "additional_kwargs", {}) or {}
    reasoning = additional.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        fields["reasoning"] = reasoning

    # Tool calls
    tool_calls = getattr(response, "tool_calls", None) or []
    if tool_calls:
        fields["tool_calls"] = tool_calls

    return fields


# ── public log functions ─────────────────────────────────────────

def log_llm_send(
    *,
    rid: str,
    model: str,
    provider: str,
    messages: list | None = None,
    tools: list | None = None,
    thinking: bool = False,
    agent_step: int | None = None,
) -> None:
    """Log an outbound LLM request with message content."""
    if not logger.isEnabledFor(logging.INFO):
        return
    tool_names = None
    if tools:
        tool_names = ",".join(
            getattr(t, "name", None) or str(t) for t in tools
        )
    header = _kv(
        rid=rid,
        model=model,
        provider=provider,
        agent_step=agent_step,
        thinking=thinking,
        tools=tool_names,
    )
    msg_detail = _format_messages(messages)
    if msg_detail:
        logger.info("[llm_send] %s\n%s", header, msg_detail)
    else:
        logger.info("[llm_send] %s", header)


def log_llm_recv(
    *,
    rid: str,
    model: str,
    provider: str,
    response: Any = None,
    content: str | None = None,
    reasoning: str | None = None,
    tool_calls: list | None = None,
    elapsed_ms: float | None = None,
    agent_step: int | None = None,
) -> None:
    """Log an inbound LLM response with content details."""
    if not logger.isEnabledFor(logging.INFO):
        return

    # Extract from response object if provided
    if response is not None:
        fields = _extract_response_fields(response)
        if content is None:
            content = fields.get("content", "")
        if reasoning is None:
            reasoning = fields.get("reasoning")
        if tool_calls is None:
            tool_calls = fields.get("tool_calls")

    header = _kv(
        rid=rid,
        model=model,
        provider=provider,
        agent_step=agent_step,
        elapsed_ms=round(elapsed_ms, 1) if elapsed_ms is not None else None,
    )
    detail_lines: list[str] = []
    if content:
        detail_lines.append(f"  content: \"{_truncate(content, _CONTENT_LIMIT)}\"")
    if reasoning:
        detail_lines.append(f"  reasoning: \"{_truncate(reasoning, _REASONING_LIMIT)}\"")
    if tool_calls:
        tc_str = json.dumps(
            [{"name": tc.get("name", "?"), "args": tc.get("args", {})} for tc in tool_calls],
            ensure_ascii=False,
            default=str,
        )
        detail_lines.append(f"  tool_calls: {_truncate(tc_str, _TOOL_ARGS_LIMIT)}")

    if detail_lines:
        logger.info("[llm_recv] %s\n%s", header, "\n".join(detail_lines))
    else:
        logger.info("[llm_recv] %s", header)


def log_tool_call(
    *,
    rid: str,
    tool_name: str,
    tool_args: dict | str | None = None,
    step: int,
) -> None:
    """Log the agent invoking a tool."""
    if not logger.isEnabledFor(logging.INFO):
        return
    header = _kv(rid=rid, tool=tool_name, step=step)
    if tool_args is not None:
        if isinstance(tool_args, dict):
            args_str = json.dumps(tool_args, ensure_ascii=False, default=str)
        else:
            args_str = str(tool_args)
        logger.info(
            "[tool_call] %s\n  args: %s",
            header,
            _truncate(args_str, _TOOL_ARGS_LIMIT),
        )
    else:
        logger.info("[tool_call] %s", header)


def log_tool_result(
    *,
    rid: str,
    tool_name: str,
    output: str,
    success: bool,
    elapsed_ms: float | None = None,
    step: int,
) -> None:
    """Log the result returned by a tool."""
    if not logger.isEnabledFor(logging.INFO):
        return
    header = _kv(
        rid=rid,
        tool=tool_name,
        step=step,
        success=success,
        elapsed_ms=round(elapsed_ms, 1) if elapsed_ms is not None else None,
    )
    logger.info(
        "[tool_result] %s\n  output: \"%s\"",
        header,
        _truncate(output, _TOOL_OUTPUT_LIMIT),
    )


def log_llm_error(
    *,
    rid: str,
    model: str,
    provider: str,
    error_type: str,
    error_detail: str,
    elapsed_ms: float | None = None,
) -> None:
    """Log an LLM call failure."""
    if not logger.isEnabledFor(logging.WARNING):
        return
    header = _kv(
        rid=rid,
        model=model,
        provider=provider,
        error_type=error_type,
        elapsed_ms=round(elapsed_ms, 1) if elapsed_ms is not None else None,
    )
    logger.warning("[llm_error] %s\n  detail: \"%s\"", header, _preview(error_detail, 200))


def log_sse_event(
    *,
    rid: str,
    model: str,
    event: dict,
) -> None:
    """Log an SSE event emitted to the frontend (replaces ``_debug_log_stream_event``)."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    evt = event.get("type", "unknown")

    if evt in {"token", "reasoning"}:
        content = event.get("content", "")
        logger.debug(
            "[sse_event] %s",
            _kv(rid=rid, model=model, evt=evt, len=len(str(content)),
                preview=f'"{_preview(content)}"'),
        )
        return

    if evt == "search_done":
        results = event.get("results", [])
        count = len(results) if isinstance(results, list) else "?"
        logger.debug("[sse_event] %s", _kv(rid=rid, model=model, evt=evt, results=count))
        return

    if evt == "context_usage":
        usage = event.get("usage", {})
        ratio = usage.get("usage_ratio") if isinstance(usage, dict) else None
        logger.debug("[sse_event] %s", _kv(rid=rid, model=model, evt=evt, usage_ratio=ratio))
        return

    if evt == "error":
        logger.debug(
            "[sse_event] %s",
            _kv(rid=rid, model=model, evt=evt, preview=f'"{_preview(event.get("error", ""))}"'),
        )
        return

    if evt == "done":
        logger.debug(
            "[sse_event] %s",
            _kv(rid=rid, model=model, evt=evt, finish_reason=event.get("finish_reason")),
        )
        return

    if evt in {"tool_call", "tool_result"}:
        logger.debug(
            "[sse_event] %s",
            _kv(rid=rid, model=model, evt=evt, tool=event.get("tool"), step=event.get("step")),
        )
        return

    if evt == "user_input_required":
        logger.debug(
            "[sse_event] %s",
            _kv(rid=rid, model=model, evt=evt, step=event.get("step"),
                preview=f'"{_preview(event.get("question", ""))}"'),
        )
        return

    logger.debug("[sse_event] %s", _kv(rid=rid, model=model, evt=evt))


def log_request_lifecycle(
    *,
    rid: str,
    model: str,
    evt: str,
    **extra: Any,
) -> None:
    """Log request-level lifecycle events (start / done / cancel)."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.debug("[lifecycle] %s", _kv(rid=rid, model=model, evt=evt, **extra))

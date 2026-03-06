"""Request schemas for the chat API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


class ValidationError(Exception):
    """Raised when request data fails validation."""

    def __init__(self, field: str, detail: str):
        self.field = field
        self.detail = detail
        super().__init__(f"{field}: {detail}")


@dataclass
class ChatRequest:
    """Parsed and validated chat request payload."""

    message: str
    history: list[dict]
    model: str | None
    enable_search: bool
    agent_mode: bool | None
    thinking_mode: bool
    images: list[str]
    request_id: str

    _MAX_MESSAGE_CHARS = 100_000
    _MAX_HISTORY_ITEMS = 100
    _MAX_IMAGE_ITEMS = 10
    _MAX_REQUEST_ID_CHARS = 256

    @classmethod
    def from_dict(cls, data: dict) -> ChatRequest:
        message = str(data.get("message", "")).strip()
        if len(message) > cls._MAX_MESSAGE_CHARS:
            raise ValidationError("message", f"too long (max {cls._MAX_MESSAGE_CHARS} chars)")

        raw_history = data.get("history", [])
        if not isinstance(raw_history, list):
            raw_history = []
        history = [
            item
            for item in raw_history[-cls._MAX_HISTORY_ITEMS:]
            if isinstance(item, dict)
            and isinstance(item.get("role"), str)
            and isinstance(item.get("content"), str)
        ]

        model = data.get("model")
        if not isinstance(model, str):
            model = None

        enable_search = bool(data.get("web_search", False))

        agent_mode = data.get("agent_mode", None)
        if not isinstance(agent_mode, bool):
            agent_mode = None

        thinking_mode = bool(data.get("thinking_mode", True))

        raw_images = data.get("images", [])
        if not isinstance(raw_images, list):
            raw_images = []
        images = [img for img in raw_images[:cls._MAX_IMAGE_ITEMS] if isinstance(img, str)]

        request_id = data.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            request_id = uuid.uuid4().hex
        elif len(request_id.strip()) > cls._MAX_REQUEST_ID_CHARS:
            raise ValidationError("request_id", f"too long (max {cls._MAX_REQUEST_ID_CHARS} chars)")
        else:
            request_id = request_id.strip()

        return cls(
            message=message,
            history=history,
            model=model,
            enable_search=enable_search,
            agent_mode=agent_mode,
            thinking_mode=thinking_mode,
            images=images,
            request_id=request_id,
        )

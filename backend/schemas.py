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

    @classmethod
    def from_dict(cls, data: dict) -> ChatRequest:
        message = str(data.get("message", "")).strip()

        history = data.get("history", [])
        if not isinstance(history, list):
            history = []

        model = data.get("model")
        if not isinstance(model, str):
            model = None

        enable_search = bool(data.get("web_search", False))

        agent_mode = data.get("agent_mode", None)
        if not isinstance(agent_mode, bool):
            agent_mode = None

        thinking_mode = bool(data.get("thinking_mode", True))

        images = data.get("images", [])
        if not isinstance(images, list):
            images = []

        request_id = data.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            request_id = uuid.uuid4().hex

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

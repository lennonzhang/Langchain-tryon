"""Message assembly, media normalization, and token estimation."""

from __future__ import annotations

from .model_registry import get_context_window, supports

_MAX_MEDIA_ITEMS = 5
_MAX_HISTORY_ITEMS = 20
_MAX_URL_DISPLAY_CHARS = 256
_CHARS_PER_TOKEN = 4
_OVERHEAD_TOKENS_PER_MSG = 4


def normalize_media_data_urls(media) -> list[str]:
    """
    Normalize media data URLs for multimodal chat.

    Notes:
    - We forward both image and video data URLs.
    - Message assembly decides `image_url` vs `video_url` payload type.
    """
    if not isinstance(media, list):
        return []

    normalized = []
    for item in media[:_MAX_MEDIA_ITEMS]:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not (value.startswith("data:image/") or value.startswith("data:video/")):
            continue
        if ";base64," not in value:
            continue
        normalized.append(value)
    return normalized


def normalize_image_data_urls(images) -> list[str]:
    """Backward-compatible alias used by older tests/callers."""
    return normalize_media_data_urls(images)


def build_user_content(model: str, message: str, media: list[str]):
    if not supports(model, "media") or not media:
        return message

    content = [{"type": "text", "text": message}]
    for url in media:
        if url.startswith("data:video/"):
            content.append({"type": "video_url", "video_url": {"url": url}})
        else:
            content.append({"type": "image_url", "image_url": {"url": url}})
    return content


def build_messages(
    model: str,
    message: str,
    history: list,
    search_context: str = "",
    images: list[str] | None = None,
) -> list[dict]:
    messages: list[dict] = []
    system_parts: list[str] = []

    if isinstance(search_context, str) and search_context.strip():
        system_parts.append(search_context)

    if isinstance(history, list):
        for item in history[-_MAX_HISTORY_ITEMS:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role == "system" and isinstance(content, str) and content.strip():
                system_parts.append(content)
                continue
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append({"role": role, "content": content})

    if system_parts:
        messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    user_content = build_user_content(model, message, images or [])
    messages.append({"role": "user", "content": user_content})
    return messages


def extract_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return "" if content is None else str(content)


def estimate_tokens_from_messages(messages: list[dict[str, str]]) -> int:
    total_chars = 0
    count = 0
    for item in messages:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            total_chars += len(content)
            count += 1
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total_chars += len(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        total_chars += len(text)
                    image_url = (part.get("image_url") or {}).get("url")
                    if isinstance(image_url, str):
                        total_chars += min(len(image_url), _MAX_URL_DISPLAY_CHARS)
                    video_url = (part.get("video_url") or {}).get("url")
                    if isinstance(video_url, str):
                        total_chars += min(len(video_url), _MAX_URL_DISPLAY_CHARS)
            count += 1

    return max(1, total_chars // _CHARS_PER_TOKEN + count * _OVERHEAD_TOKENS_PER_MSG)


def context_usage_payload(model: str, phase: str, messages: list[dict[str, str]]) -> dict:
    window_total = get_context_window(model)
    used = estimate_tokens_from_messages(messages)
    ratio = used / window_total if window_total > 0 else 0.0
    return {
        "model": model,
        "phase": phase,
        "used_estimated_tokens": used,
        "window_total_tokens": window_total,
        "usage_ratio": round(ratio, 4),
    }


def history_as_messages(history: list) -> list:
    """Convert frontend history dicts to LangChain Message objects."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    _ROLE_MAP = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}

    if not isinstance(history, list):
        return []

    messages = []
    for item in history[-_MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        cls = _ROLE_MAP.get(role)
        if cls and isinstance(content, str):
            messages.append(cls(content=content))
    return messages


def history_as_text(history: list) -> str:
    if not isinstance(history, list):
        return ""

    lines = []
    for item in history[-_MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant", "system"} and isinstance(content, str):
            lines.append(f"{role}: {content}")
    return "\n".join(lines)

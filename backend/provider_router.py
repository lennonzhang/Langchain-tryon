"""Provider routing helpers for chat model construction."""

from __future__ import annotations

from .model_registry import get_provider
from .model_profile import build_chat_model


def build_routed_chat_model(api_key: str, model: str, thinking_mode: bool = True):
    """Build a provider-specific chat model while keeping facade stable."""
    provider = get_provider(model)
    return build_chat_model(
        api_key=api_key,
        model=model,
        thinking_mode=thinking_mode,
        provider=provider,
    )

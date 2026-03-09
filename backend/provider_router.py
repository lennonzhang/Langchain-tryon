"""Provider routing helpers for chat model construction."""

from __future__ import annotations

from backend.domain.model_catalog import catalog
from backend.model_profile import build_chat_model


def build_routed_chat_model(api_key: str, model: str, thinking_mode: bool = True):
    provider = catalog.get_provider(model)
    return build_chat_model(
        api_key=api_key,
        model=model,
        thinking_mode=thinking_mode,
        provider=provider,
    )

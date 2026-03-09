"""Compatibility facade over chat model factory and runtime settings."""

from __future__ import annotations

from backend.infrastructure.chat_model_factory import (
    _build_nvidia_chat_model,
    chat_model_factory,
    output_tokens,
    proxy_env_guard,
    stream_or_invoke_kwargs,
)


def int_env(name: str, default: int, min_value: int) -> int:
    from backend.settings.env_loader import env_int

    return env_int(name, default, min_value)


def float_env(name: str, default: float, min_value: float) -> float:
    from backend.settings.env_loader import env_float

    return env_float(name, default, min_value)


def build_chat_model(
    api_key: str,
    model: str,
    thinking_mode: bool = True,
    provider: str = "nvidia",
):
    return chat_model_factory.build(
        api_key=api_key,
        model=model,
        thinking_mode=thinking_mode,
        provider=provider,
    )

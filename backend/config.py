from __future__ import annotations

from pathlib import Path

from backend.application.chat_use_cases import resolve_model
from backend.infrastructure.provider_settings import (
    normalize_provider_base_url,
    resolve_model_api_key,
    resolve_provider_settings,
)
from backend.settings.env_loader import load_env_file


API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def load_api_key(base_dir: Path | None = None) -> str:
    return resolve_model_api_key(base_dir)


def provider_credentials(provider: str, fallback_api_key: str | None = None) -> tuple[str, str | None]:
    settings = resolve_provider_settings(provider, fallback_api_key=fallback_api_key)
    return settings.api_key, settings.base_url


def provider_ssl_verify(provider: str) -> bool:
    return resolve_provider_settings(provider).ssl_verify


__all__ = [
    "API_URL",
    "load_api_key",
    "load_env_file",
    "normalize_provider_base_url",
    "provider_credentials",
    "provider_ssl_verify",
    "resolve_model",
]

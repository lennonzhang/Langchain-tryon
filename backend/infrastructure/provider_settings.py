from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.settings.env_loader import load_env_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    api_key: str
    base_url: str | None
    ssl_verify: bool


def _provider_env_key(provider_key: str, suffix: str) -> str:
    return f"{provider_key.upper()}_{suffix}"


def _default_base_url(provider: str) -> str | None:
    if provider in {"anthropic", "openai"}:
        return "https://claude2.sssaicode.com/api/v1"
    if provider == "google":
        return "https://claude2.sssaicode.com/api/v1beta"
    return None


def normalize_provider_base_url(provider: str, base_url: str | None) -> str | None:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return _default_base_url(provider)

    if provider in {"anthropic", "openai"} and url.endswith("/api"):
        return f"{url}/v1"
    if provider == "google" and url.endswith("/api"):
        return f"{url}/v1beta"
    return url


def resolve_model_api_key(base_dir: Path | None = None) -> str:
    root = base_dir or Path(__file__).resolve().parents[2]
    load_env_file(root)

    env_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if env_key:
        return env_key

    for key_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        fallback = os.getenv(key_name, "").strip()
        if fallback:
            return fallback

    raise RuntimeError("No API key found. Set NVIDIA_API_KEY in system env or .env.")


def resolve_provider_settings(provider: str, fallback_api_key: str | None = None) -> ProviderSettings:
    provider_key = str(provider or "nvidia").lower()
    load_env_file()

    if provider_key == "anthropic":
        api_key = (
            os.getenv("ANTHROPIC_API_KEY", "").strip()
            or os.getenv("CLAUDE_CLIENT_TOKEN_1", "").strip()
            or os.getenv("CLAUDE_CLIENT_TOKEN", "").strip()
            or (fallback_api_key or "").strip()
        )
        base_url = (
            os.getenv("ANTHROPIC_BASE_URL", "").strip()
            or os.getenv("CLAUDE_API_URL", "").strip()
            or None
        )
    elif provider_key == "openai":
        api_key = (
            os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("CODEX_TOKEN_1", "").strip()
            or os.getenv("CODEX_TOKEN", "").strip()
            or (fallback_api_key or "").strip()
        )
        base_url = (
            os.getenv("OPENAI_BASE_URL", "").strip()
            or os.getenv("CODEX_API_URL", "").strip()
            or None
        )
    elif provider_key == "google":
        api_key = (
            os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY_1", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
            or (fallback_api_key or "").strip()
        )
        base_url = (
            os.getenv("GOOGLE_BASE_URL", "").strip()
            or os.getenv("GOOGLE_GEMINI_BASE_URL", "").strip()
            or None
        )
    else:
        api_key = os.getenv("NVIDIA_API_KEY", "").strip() or (fallback_api_key or "").strip()
        base_url = os.getenv("NVIDIA_BASE_URL", "").strip() or None

    ssl_verify = os.getenv(_provider_env_key(provider_key, "SSL_VERIFY"), "true").strip().lower() not in (
        "false",
        "0",
        "no",
    )
    if not ssl_verify:
        logger.warning("SSL verification disabled for provider '%s'", provider_key)

    return ProviderSettings(
        provider=provider_key,
        api_key=api_key,
        base_url=normalize_provider_base_url(provider_key, base_url),
        ssl_verify=ssl_verify,
    )


def resolve_provider_timeout(provider: str, default_seconds: float = 300.0) -> float:
    provider_key = str(provider or "nvidia").lower()
    load_env_file()
    provider_raw = os.getenv(_provider_env_key(provider_key, "TIMEOUT_SECONDS"), "").strip()
    shared_raw = os.getenv("MODEL_TIMEOUT_SECONDS", "").strip()

    for raw in (provider_raw, shared_raw):
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        return max(30.0, value)
    return default_seconds


def resolve_openai_sse_read_timeout(default_seconds: float = 600.0) -> float:
    load_env_file()
    raw = os.getenv("OPENAI_SSE_READ_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return default_seconds
    try:
        value = float(raw)
    except ValueError:
        return default_seconds
    return max(30.0, value)

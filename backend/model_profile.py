"""Model construction, environment helpers, and invocation parameters."""

from __future__ import annotations

import os
from contextlib import contextmanager

from .config import provider_credentials
from .model_registry import get_params
from .model_registry import get_upstream_model
from .proxy_chat_model import ProxyGatewayChatModel

_MAX_COMPLETION_TOKENS_LIMIT = 16384


def int_env(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def float_env(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def output_tokens() -> int:
    requested = int_env("NVIDIA_MAX_COMPLETION_TOKENS", _MAX_COMPLETION_TOKENS_LIMIT, 256)
    return min(requested, _MAX_COMPLETION_TOKENS_LIMIT)


@contextmanager
def proxy_env_guard():
    use_system_proxy = os.getenv("NVIDIA_USE_SYSTEM_PROXY", "").strip() == "1"
    if use_system_proxy:
        yield
        return

    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]
    backup = {key: os.environ.get(key) for key in proxy_keys}

    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _build_nvidia_chat_model(api_key: str, upstream_model: str, model: str, thinking_mode: bool, pcfg: dict):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "LangChain NVIDIA package missing. Activate .venv and install requirements.txt first."
        ) from exc

    timeout_seconds = float_env("NVIDIA_TIMEOUT_SECONDS", 300.0, 30.0)

    if thinking_mode:
        temperature = pcfg.get("temperature_thinking", 1.0)
    else:
        temperature = pcfg.get("temperature_standard", 0.6)
    top_p = pcfg.get("top_p", 1.0)

    params = {
        "model": upstream_model,
        "api_key": api_key,
        "temperature": temperature,
        "top_p": top_p,
        "max_completion_tokens": output_tokens(),
        "timeout": timeout_seconds,
    }

    if pcfg.get("thinking_control") == "construct_time":
        params["extra_body"] = {
            "chat_template_kwargs": {
                "enable_thinking": bool(thinking_mode),
                "clear_thinking": not bool(thinking_mode),
            }
        }

    return ChatNVIDIA(**params)


def _normalize_proxy_base_url(provider: str, base_url: str | None) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        if provider in {"anthropic", "openai"}:
            return "https://claude2.sssaicode.com/api/v1"
        if provider == "google":
            return "https://claude2.sssaicode.com/api/v1beta"
        return ""

    if provider in {"anthropic", "openai"} and url.endswith("/api"):
        return f"{url}/v1"
    if provider == "google" and url.endswith("/api"):
        return f"{url}/v1beta"
    return url


def build_chat_model(
    api_key: str,
    model: str,
    thinking_mode: bool = True,
    provider: str = "nvidia",
):
    timeout_seconds = float_env("NVIDIA_TIMEOUT_SECONDS", 300.0, 30.0)
    pcfg = get_params(model)
    upstream_model = get_upstream_model(model)

    if thinking_mode:
        temperature = pcfg.get("temperature_thinking", 1.0)
    else:
        temperature = pcfg.get("temperature_standard", 0.6)
    top_p = pcfg.get("top_p", 1.0)

    resolved_api_key, base_url = provider_credentials(provider, fallback_api_key=api_key)
    if not resolved_api_key:
        raise RuntimeError(f"Missing API key for provider '{provider}'.")

    provider_key = str(provider).lower()
    if provider_key == "nvidia":
        return _build_nvidia_chat_model(
            api_key=resolved_api_key,
            upstream_model=upstream_model,
            model=model,
            thinking_mode=thinking_mode,
            pcfg=pcfg,
        )
    if provider_key == "anthropic":
        return ProxyGatewayChatModel(
            provider="anthropic",
            api_key=resolved_api_key,
            model=upstream_model,
            base_url=_normalize_proxy_base_url("anthropic", base_url),
            timeout=timeout_seconds,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=output_tokens(),
            thinking_mode=thinking_mode,
        )
    if provider_key == "openai":
        return ProxyGatewayChatModel(
            provider="openai",
            api_key=resolved_api_key,
            model=upstream_model,
            base_url=_normalize_proxy_base_url("openai", base_url),
            timeout=timeout_seconds,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=output_tokens(),
            thinking_mode=thinking_mode,
        )
    if provider_key == "google":
        return ProxyGatewayChatModel(
            provider="google",
            api_key=resolved_api_key,
            model=upstream_model,
            base_url=_normalize_proxy_base_url("google", base_url),
            timeout=timeout_seconds,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=output_tokens(),
            thinking_mode=thinking_mode,
        )
    raise RuntimeError(f"Unsupported provider '{provider}'.")


def stream_or_invoke_kwargs(model: str, thinking_mode: bool) -> dict:
    kwargs = {"max_completion_tokens": output_tokens()}
    pcfg = get_params(model)
    if pcfg.get("thinking_control") == "call_time":
        field = pcfg.get("thinking_kwarg_field", "thinking")
        kwargs["chat_template_kwargs"] = {field: bool(thinking_mode)}
    return kwargs

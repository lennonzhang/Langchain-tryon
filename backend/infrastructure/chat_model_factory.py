from __future__ import annotations

import os
from contextlib import contextmanager

from backend.domain.model_catalog import catalog
from backend.infrastructure.provider_settings import resolve_provider_settings, resolve_provider_timeout
from backend.settings.env_loader import env_float, env_int

from backend.proxy_chat_model import ProxyGatewayChatModel

_MAX_COMPLETION_TOKENS_LIMIT = 16384


def output_tokens() -> int:
    requested = env_int("NVIDIA_MAX_COMPLETION_TOKENS", _MAX_COMPLETION_TOKENS_LIMIT, 256)
    return min(requested, _MAX_COMPLETION_TOKENS_LIMIT)


@contextmanager
def proxy_env_guard():
    use_system_proxy = os.getenv("NVIDIA_USE_SYSTEM_PROXY", "").strip() == "1"
    if use_system_proxy:
        yield
        return

    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]
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


def stream_or_invoke_kwargs(model: str, thinking_mode: bool) -> dict:
    kwargs = {"max_completion_tokens": output_tokens()}
    params = catalog.get_params(model)
    if params.get("thinking_control") == "call_time":
        field = params.get("thinking_kwarg_field", "thinking")
        kwargs["chat_template_kwargs"] = {field: bool(thinking_mode)}
    return kwargs


def _build_nvidia_chat_model(api_key: str, upstream_model: str, thinking_mode: bool, params: dict):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "LangChain NVIDIA package missing. Activate .venv and install requirements.txt first."
        ) from exc

    timeout_seconds = env_float("NVIDIA_TIMEOUT_SECONDS", 300.0, 30.0)
    temperature = params.get("temperature_thinking", 1.0) if thinking_mode else params.get("temperature_standard", 0.6)
    kwargs = {
        "model": upstream_model,
        "api_key": api_key,
        "temperature": temperature,
        "top_p": params.get("top_p", 1.0),
        "max_completion_tokens": output_tokens(),
        "timeout": timeout_seconds,
    }
    if params.get("thinking_control") == "construct_time":
        kwargs["extra_body"] = {
            "chat_template_kwargs": {
                "enable_thinking": bool(thinking_mode),
                "clear_thinking": not bool(thinking_mode),
            }
        }
    return ChatNVIDIA(**kwargs)


class ChatModelFactory:
    def build(self, api_key: str, model: str, thinking_mode: bool = True, provider: str = "nvidia"):
        timeout_seconds = resolve_provider_timeout(provider, default_seconds=300.0)
        params = catalog.get_params(model)
        upstream_model = catalog.get_upstream_model(model)
        temperature = params.get("temperature_thinking", 1.0) if thinking_mode else params.get(
            "temperature_standard", 0.6
        )
        top_p = params.get("top_p", 1.0)
        settings = resolve_provider_settings(provider, fallback_api_key=api_key)
        if not settings.api_key:
            raise RuntimeError(f"Missing API key for provider '{provider}'.")
        if settings.provider == "nvidia":
            return _build_nvidia_chat_model(settings.api_key, upstream_model, thinking_mode, params)
        return ProxyGatewayChatModel(
            provider=settings.provider,
            model=upstream_model,
            api_key=settings.api_key,
            base_url=settings.base_url or "",
            timeout=timeout_seconds,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=output_tokens(),
            thinking_mode=thinking_mode,
            ssl_verify=settings.ssl_verify,
        )


chat_model_factory = ChatModelFactory()

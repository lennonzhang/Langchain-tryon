"""Model construction, environment helpers, and invocation parameters."""

from __future__ import annotations

import os
from contextlib import contextmanager

from .model_registry import get_params

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


def build_chat_model(api_key: str, model: str, thinking_mode: bool = True):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "LangChain NVIDIA package missing. Activate .venv and install requirements.txt first."
        ) from exc

    timeout_seconds = float_env("NVIDIA_TIMEOUT_SECONDS", 300.0, 30.0)
    pcfg = get_params(model)

    if thinking_mode:
        temperature = pcfg.get("temperature_thinking", 1.0)
    else:
        temperature = pcfg.get("temperature_standard", 0.6)
    top_p = pcfg.get("top_p", 1.0)

    params = {
        "model": model,
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


def stream_or_invoke_kwargs(model: str, thinking_mode: bool) -> dict:
    kwargs = {"max_completion_tokens": output_tokens()}
    pcfg = get_params(model)
    if pcfg.get("thinking_control") == "call_time":
        field = pcfg.get("thinking_kwarg_field", "thinking")
        kwargs["chat_template_kwargs"] = {field: bool(thinking_mode)}
    return kwargs

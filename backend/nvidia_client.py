import os
from contextlib import contextmanager

from .config import MODEL, resolve_model


@contextmanager
def _proxy_env_guard():
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


def _build_chat_model(api_key: str, model: str):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "LangChain NVIDIA package missing. Activate .venv and install requirements.txt first."
        ) from exc

    params = {
        "model": model,
        "api_key": api_key,
        "temperature": 1,
        "top_p": 1,
        "max_tokens": 16384,
    }

    # GLM prefers explicit thinking controls in request body.
    if model.startswith("z-ai/"):
        params["extra_body"] = {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False,
            }
        }

    return ChatNVIDIA(**params)


def _build_messages(
    message: str, history: list, search_context: str = ""
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    if search_context:
        messages.append({"role": "system", "content": search_context})

    if isinstance(history, list):
        for item in history[-20:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant", "system"} and isinstance(content, str):
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})
    return messages


def _extract_text(content) -> str:
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


def _run_web_search(message: str):
    """Execute web search and return (context_str, results_list) or ("", [])."""
    from .web_search import format_search_context, web_search

    results = web_search(message, num_results=5)
    context = format_search_context(message, results)
    return context, results


def chat_once(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
) -> str:
    chosen_model = resolve_model(model)
    client = _build_chat_model(api_key, chosen_model)

    search_context = ""
    if enable_search:
        search_context, _ = _run_web_search(message)

    messages = _build_messages(message, history, search_context)

    with _proxy_env_guard():
        response = client.invoke(messages)

    return _extract_text(getattr(response, "content", ""))


def stream_chat(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
):
    chosen_model = resolve_model(model)
    client = _build_chat_model(api_key, chosen_model)

    search_context = ""
    if enable_search:
        yield {"type": "search_start", "query": message}
        try:
            search_context, results = _run_web_search(message)
            yield {"type": "search_done", "results": results}
        except Exception as exc:  # noqa: BLE001
            yield {"type": "search_error", "error": str(exc)}

    messages = _build_messages(message, history, search_context)

    stream_kwargs = {}
    if chosen_model.startswith("moonshotai/"):
        stream_kwargs["chat_template_kwargs"] = {"thinking": True}

    with _proxy_env_guard():
        for chunk in client.stream(messages, **stream_kwargs):
            additional = getattr(chunk, "additional_kwargs", {}) or {}
            reasoning = additional.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                yield {"type": "reasoning", "content": reasoning}

            token = _extract_text(getattr(chunk, "content", ""))
            if token:
                yield {"type": "token", "content": token}

    yield {"type": "done", "finish_reason": "stop"}
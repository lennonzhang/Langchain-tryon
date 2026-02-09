import os
from contextlib import contextmanager

from .config import MODEL


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


def _build_chat_model(api_key: str):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "LangChain NVIDIA package missing. Activate .venv and install requirements.txt first."
        ) from exc

    return ChatNVIDIA(
        model=MODEL,
        api_key=api_key,
        max_tokens=8196,
        temperature=1.0,
        top_p=1.0,
    )


def _to_langchain_messages(message: str, history: list):
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except ImportError as exc:
        raise RuntimeError(
            "LangChain core package missing. Activate .venv and install requirements.txt first."
        ) from exc

    messages = []
    if isinstance(history, list):
        for item in history[-20:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if not isinstance(content, str):
                continue

            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            elif role == "system":
                messages.append(SystemMessage(content=content))

    messages.append(HumanMessage(content=message))
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


def chat_once(api_key: str, message: str, history: list) -> str:
    llm = _build_chat_model(api_key)
    messages = _to_langchain_messages(message, history)

    with _proxy_env_guard():
        response = llm.invoke(messages)

    return _extract_text(getattr(response, "content", ""))


def stream_chat(api_key: str, message: str, history: list):
    llm = _build_chat_model(api_key)
    messages = _to_langchain_messages(message, history)

    with _proxy_env_guard():
        for chunk in llm.stream(messages):
            token = _extract_text(getattr(chunk, "content", ""))
            if token:
                yield {"type": "token", "content": token}

    yield {"type": "done", "finish_reason": "stop"}
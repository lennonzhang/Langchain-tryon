import json
import os
from urllib import error, request

from .config import API_URL, MODEL


def _open_request(req: request.Request, timeout: int):
    use_system_proxy = os.getenv("NVIDIA_USE_SYSTEM_PROXY", "").strip() == "1"
    if use_system_proxy:
        return request.urlopen(req, timeout=timeout)

    # Ignore global proxy env vars by default; local invalid proxies are common.
    opener = request.build_opener(request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def build_messages(message: str, history: list) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
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


def chat_once(api_key: str, message: str, history: list) -> str:
    payload = {
        "model": MODEL,
        "messages": build_messages(message, history),
        "max_tokens": 8196,
        "temperature": 1.00,
        "top_p": 1.0,
        "stream": False,
    }

    req = request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    with _open_request(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected response format: {data}") from exc


def stream_chat(api_key: str, message: str, history: list):
    payload = {
        "model": MODEL,
        "messages": build_messages(message, history),
        "max_tokens": 8196,
        "temperature": 1.00,
        "top_p": 1.0,
        "stream": True,
        "chat_template_kwargs": {"thinking": True},
    }

    req = request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    try:
        with _open_request(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue

                data = line[5:].strip()
                if data == "[DONE]":
                    yield {"type": "done"}
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                token = delta.get("content")
                reasoning = delta.get("reasoning_content")

                if isinstance(token, str) and token:
                    yield {"type": "token", "content": token}
                if isinstance(reasoning, str) and reasoning:
                    yield {"type": "reasoning", "content": reasoning}

                finish_reason = choice.get("finish_reason")
                if finish_reason:
                    yield {"type": "done", "finish_reason": finish_reason}
                    break
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Upstream HTTP error: {detail[:500]}") from exc
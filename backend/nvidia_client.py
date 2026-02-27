import os
import queue
import threading
from contextlib import contextmanager

from .config import resolve_model

_MODEL_CONTEXT_WINDOW = {
    "moonshotai/kimi-k2.5": 131072,
    "qwen/qwen3.5-397b-a17b": 128000,
    "z-ai/glm5": 128000,
}
_MAX_COMPLETION_TOKENS_LIMIT = 16384
_AGENT_MAX_STEPS = 3


def _int_env(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def _float_env(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def _output_tokens() -> int:
    requested = _int_env("NVIDIA_MAX_COMPLETION_TOKENS", _MAX_COMPLETION_TOKENS_LIMIT, 256)
    return min(requested, _MAX_COMPLETION_TOKENS_LIMIT)


def _normalize_media_data_urls(media) -> list[str]:
    """
    Normalize media data URLs for multimodal chat.

    Notes:
    - We forward both image and video data URLs.
    - Message assembly decides `image_url` vs `video_url` payload type.
    """
    if not isinstance(media, list):
        return []

    normalized = []
    for item in media[:5]:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not (value.startswith("data:image/") or value.startswith("data:video/")):
            continue
        if ";base64," not in value:
            continue
        normalized.append(value)
    return normalized


def _normalize_image_data_urls(images) -> list[str]:
    """Backward-compatible alias used by older tests/callers."""
    return _normalize_media_data_urls(images)


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


def _build_chat_model(api_key: str, model: str, thinking_mode: bool = True):
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise RuntimeError(
            "LangChain NVIDIA package missing. Activate .venv and install requirements.txt first."
        ) from exc

    timeout_seconds = _float_env("NVIDIA_TIMEOUT_SECONDS", 300.0, 30.0)
    temperature = 1.0
    top_p = 1.0
    if model.startswith("moonshotai/"):
        temperature = 1.0 if thinking_mode else 0.6
    elif model.startswith("qwen/"):
        temperature = 0.6
        top_p = 0.95
    elif model.startswith("z-ai/"):
        temperature = 0.7

    params = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "top_p": top_p,
        "max_completion_tokens": _output_tokens(),
        "timeout": timeout_seconds,
    }

    if model.startswith("z-ai/"):
        params["extra_body"] = {
            "chat_template_kwargs": {
                "enable_thinking": bool(thinking_mode),
                "clear_thinking": not bool(thinking_mode),
            }
        }

    return ChatNVIDIA(**params)


def _build_user_content(model: str, message: str, media: list[str]):
    if not _supports_images(model) or not media:
        return message

    content = [{"type": "text", "text": message}]
    for url in media:
        if url.startswith("data:video/"):
            content.append({"type": "video_url", "video_url": {"url": url}})
        else:
            content.append({"type": "image_url", "image_url": {"url": url}})
    return content


def _build_messages(
    model: str,
    message: str,
    history: list,
    search_context: str = "",
    images: list[str] | None = None,
) -> list[dict]:
    messages: list[dict] = []

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

    user_content = _build_user_content(model, message, images or [])
    messages.append({"role": "user", "content": user_content})
    return messages


def _supports_thinking(model: str) -> bool:
    return (
        model.startswith("moonshotai/")
        or model.startswith("qwen/")
        or model.startswith("z-ai/")
    )


def _supports_images(model: str) -> bool:
    return model.startswith("moonshotai/")


def _is_agentic_model(model: str) -> bool:
    return model.startswith("qwen/") or model.startswith("z-ai/")


def _should_use_agentic_flow(model: str, agent_mode: bool) -> bool:
    return _is_agentic_model(model) and bool(agent_mode)


def _stream_or_invoke_kwargs(model: str, thinking_mode: bool) -> dict:
    kwargs = {"max_completion_tokens": _output_tokens()}
    if model.startswith("moonshotai/"):
        kwargs["chat_template_kwargs"] = {"thinking": bool(thinking_mode)}
    elif model.startswith("qwen/"):
        kwargs["chat_template_kwargs"] = {"enable_thinking": bool(thinking_mode)}
    return kwargs


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


def _estimate_tokens_from_messages(messages: list[dict[str, str]]) -> int:
    total_chars = 0
    count = 0
    for item in messages:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            total_chars += len(content)
            count += 1
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total_chars += len(part)
                    continue
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        total_chars += len(text)
                    image_url = (part.get("image_url") or {}).get("url")
                    if isinstance(image_url, str):
                        total_chars += min(len(image_url), 256)
                    video_url = (part.get("video_url") or {}).get("url")
                    if isinstance(video_url, str):
                        total_chars += min(len(video_url), 256)
            count += 1

    return max(1, total_chars // 4 + count * 4)


def _context_usage_payload(model: str, phase: str, messages: list[dict[str, str]]) -> dict:
    window_total = _MODEL_CONTEXT_WINDOW.get(model, 128000)
    used = _estimate_tokens_from_messages(messages)
    ratio = used / window_total if window_total > 0 else 0.0
    return {
        "model": model,
        "phase": phase,
        "used_estimated_tokens": used,
        "window_total_tokens": window_total,
        "usage_ratio": round(ratio, 4),
    }


def _run_web_search(
    message: str,
    num_results: int = 5,
    include_page_content: bool = True,
):
    """Execute web search and return (context_str, results_list) or ("", [])."""
    from .web_search import format_search_context, web_search

    results = web_search(
        message,
        num_results=num_results,
        include_page_content=include_page_content,
    )
    context = format_search_context(message, results)
    return context, results


def _history_as_text(history: list) -> str:
    if not isinstance(history, list):
        return ""

    lines = []
    for item in history[-20:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant", "system"} and isinstance(content, str):
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _run_langchain_react_agent(
    client,
    model: str,
    message: str,
    history: list,
    thinking_mode: bool,
    event_collector: list[dict] | None = None,
    event_emitter=None,
    emit_reasoning: bool = False,
) -> str:
    from langchain.agents import AgentExecutor, create_react_agent
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.prompts import PromptTemplate
    from langchain_core.tools import tool

    def _emit_event(event: dict):
        if isinstance(event_collector, list):
            event_collector.append(event)
        if callable(event_emitter):
            event_emitter(event)

    class _AgentEventHandler(BaseCallbackHandler):
        def __init__(self, enabled: bool):
            self.enabled = enabled

        def on_llm_end(self, response, **kwargs):
            if not self.enabled:
                return
            generations = getattr(response, "generations", None)
            if not isinstance(generations, list):
                return
            for generation_group in generations:
                if not isinstance(generation_group, list):
                    continue
                for generation in generation_group:
                    message_obj = getattr(generation, "message", None)
                    additional = getattr(message_obj, "additional_kwargs", {}) or {}
                    reasoning = additional.get("reasoning_content")
                    if isinstance(reasoning, str) and reasoning:
                        _emit_event({"type": "reasoning", "content": reasoning})

    prompt = PromptTemplate.from_template(
        """You are a helpful agent that can use tools.

You have access to the following tools:
{tools}

Use the following format:
Question: the input question you must answer
Thought: think about what to do next
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Conversation history:
{chat_history}

Question: {input}
Thought:{agent_scratchpad}"""
    )

    @tool("web_search")
    def web_search_tool(query: str) -> str:
        """Search the web for up-to-date information."""
        _emit_event({"type": "search_start", "query": query})
        try:
            context, results = _run_web_search(query)
            _emit_event({"type": "search_done", "results": results})
            return context or "No useful search results."
        except Exception as exc:  # noqa: BLE001
            _emit_event({"type": "search_error", "error": str(exc)})
            return f"Search error: {exc}"

    llm = client.bind(**_stream_or_invoke_kwargs(model, thinking_mode))
    tools = [web_search_tool]
    agent = create_react_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=_AGENT_MAX_STEPS,
        handle_parsing_errors=True,
        return_intermediate_steps=False,
        verbose=False,
    )

    callbacks = [_AgentEventHandler(bool(emit_reasoning))]
    result = executor.invoke(
        {
            "input": message,
            "chat_history": _history_as_text(history),
        },
        config={"callbacks": callbacks},
    )
    output = result.get("output", "")
    return output.strip() if isinstance(output, str) else str(output)


def chat_once(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
    agent_mode: bool = False,
    thinking_mode: bool = True,
    images: list[str] | None = None,
) -> str:
    chosen_model = resolve_model(model)
    client = _build_chat_model(api_key, chosen_model, thinking_mode=thinking_mode)

    if _should_use_agentic_flow(chosen_model, agent_mode):
        agent_events: list[dict] = []
        with _proxy_env_guard():
            return _run_langchain_react_agent(
                client=client,
                model=chosen_model,
                message=message,
                history=history,
                thinking_mode=thinking_mode,
                event_collector=agent_events,
            )

    initial_search_context = ""
    if enable_search:
        initial_search_context, _ = _run_web_search(message)

    normalized_images = _normalize_media_data_urls(images)
    messages = _build_messages(
        chosen_model,
        message,
        history,
        initial_search_context,
        normalized_images,
    )

    with _proxy_env_guard():
        response = client.invoke(
            messages,
            **_stream_or_invoke_kwargs(chosen_model, thinking_mode),
        )

    return _extract_text(getattr(response, "content", ""))


def stream_chat(
    api_key: str,
    message: str,
    history: list,
    model: str | None = None,
    enable_search: bool = False,
    agent_mode: bool = False,
    thinking_mode: bool = True,
    images: list[str] | None = None,
):
    chosen_model = resolve_model(model)
    client = _build_chat_model(api_key, chosen_model, thinking_mode=thinking_mode)
    emit_reasoning = _supports_thinking(chosen_model) and bool(thinking_mode)

    if _should_use_agentic_flow(chosen_model, agent_mode):
        agent_events: list[dict] = []
        result_queue: queue.Queue = queue.Queue()
        state = {"final_answer": "", "error": None}

        def _emit_from_agent(event: dict):
            result_queue.put(event)

        def _run_agent():
            try:
                with _proxy_env_guard():
                    state["final_answer"] = _run_langchain_react_agent(
                        client=client,
                        model=chosen_model,
                        message=message,
                        history=history,
                        thinking_mode=thinking_mode,
                        event_collector=agent_events,
                        event_emitter=_emit_from_agent,
                        emit_reasoning=emit_reasoning,
                    )
            except Exception as exc:  # noqa: BLE001
                state["error"] = exc

        worker = threading.Thread(target=_run_agent, daemon=True)
        worker.start()

        yield {
            "type": "context_usage",
            "usage": _context_usage_payload(
                chosen_model,
                "agent",
                _build_messages(chosen_model, message, history, "", []),
            ),
        }

        while worker.is_alive() or not result_queue.empty():
            try:
                evt = result_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if isinstance(evt, dict) and evt.get("type"):
                yield evt

        if state["error"] is not None:
            yield {"type": "error", "error": str(state["error"])}
            yield {"type": "done", "finish_reason": "error"}
            return

        if state["final_answer"]:
            yield {"type": "token", "content": state["final_answer"]}
        yield {"type": "done", "finish_reason": "stop"}
        return

    initial_search_context = ""
    if enable_search:
        yield {"type": "search_start", "query": message}
        try:
            initial_search_context, results = _run_web_search(message)
            yield {"type": "search_done", "results": results}
        except Exception as exc:  # noqa: BLE001
            yield {"type": "search_error", "error": str(exc)}

    normalized_images = _normalize_media_data_urls(images)
    messages = _build_messages(
        chosen_model,
        message,
        history,
        initial_search_context,
        normalized_images,
    )

    stream_kwargs = _stream_or_invoke_kwargs(chosen_model, thinking_mode)

    with _proxy_env_guard():
        yield {
            "type": "context_usage",
            "usage": _context_usage_payload(chosen_model, "single", messages),
        }

        for chunk in client.stream(messages, **stream_kwargs):
            additional = getattr(chunk, "additional_kwargs", {}) or {}
            reasoning = additional.get("reasoning_content")
            if emit_reasoning and isinstance(reasoning, str) and reasoning:
                yield {"type": "reasoning", "content": reasoning}

            token = _extract_text(getattr(chunk, "content", ""))
            if token:
                yield {"type": "token", "content": token}

    yield {"type": "done", "finish_reason": "stop"}

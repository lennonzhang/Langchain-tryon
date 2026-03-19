from __future__ import annotations

import threading
import time

from backend.chat_logger import log_llm_recv, log_llm_send, log_request_lifecycle
from backend.domain.execution import (
    CancellationRegistry,
    ChatExecutionContext,
    EventSink,
    SseEventStream,
)
from backend.domain.model_catalog import catalog
from backend.application.search_service import SearchService
from backend.event_mapper import stream_agentic, stream_direct
from backend.infrastructure.chat_model_factory import proxy_env_guard, stream_or_invoke_kwargs
from backend.message_builder import build_messages, extract_text, normalize_media_data_urls


def resolve_model(model: str | None) -> str:
    resolved = catalog.get_by_id(model)
    if resolved is not None:
        return resolved["id"]
    return catalog.get_default()["id"]


def should_use_agentic_flow(model: str, agent_mode: bool | None) -> bool:
    if agent_mode is False:
        return False
    return catalog.supports(model, "agent")


class ChatUseCaseDependencies:
    def __init__(
        self,
        run_web_search,
        run_agent,
        *,
        build_chat_model,
        resolve_model,
        search_service: SearchService | None = None,
        registry: CancellationRegistry | None = None,
    ):
        self.run_web_search = run_web_search
        self.run_agent = run_agent
        self.build_chat_model = build_chat_model
        self.resolve_model = resolve_model
        self.search_service = search_service or SearchService(run_web_search)
        self.registry = registry or CancellationRegistry()


class ChatOnceUseCase:
    def __init__(self, deps: ChatUseCaseDependencies):
        self._deps = deps

    def execute(
        self,
        *,
        api_key: str,
        message: str,
        history: list,
        model: str | None,
        enable_search: bool,
        agent_mode: bool | None,
        thinking_mode: bool,
        images: list[str] | None,
        request_id: str,
    ) -> str:
        resolved_model = self._deps.resolve_model(model)
        token = self._deps.registry.register(request_id, kind="once")
        ctx = ChatExecutionContext(
            request_id=request_id,
            resolved_model=resolved_model,
            provider=catalog.get_provider(resolved_model),
            protocol=catalog.get_protocol(resolved_model),
            thinking_mode=thinking_mode,
            agent_mode=agent_mode,
            enable_search=enable_search,
            cancel_token=token,
        )
        log_request_lifecycle(
            rid=ctx.request_id, model=ctx.resolved_model, evt="once_start",
            agent_mode=ctx.agent_mode, thinking=ctx.thinking_mode,
        )
        try:
            client = self._deps.build_chat_model(
                api_key,
                ctx.resolved_model,
                thinking_mode=ctx.thinking_mode,
            )
            if should_use_agentic_flow(ctx.resolved_model, ctx.agent_mode):
                collected_tokens: list[str] = []
                clarification_question: str | None = None

                def collect(event: dict) -> None:
                    nonlocal clarification_question
                    if ctx.cancel_token.cancelled:
                        return
                    if event.get("type") == "token":
                        collected_tokens.append(event.get("content", ""))
                    elif event.get("type") == "user_input_required":
                        question = str(event.get("question") or "").strip()
                        clarification_question = question or "Please provide the missing information."

                search_provider = self._deps.search_service.provider(lambda _evt: None, cancel_token=ctx.cancel_token)
                with proxy_env_guard():
                    self._deps.run_agent(
                        client=client,
                        model=ctx.resolved_model,
                        message=message,
                        history=history,
                        thinking_mode=ctx.thinking_mode,
                        search_provider=search_provider,
                        event_emitter=collect,
                        cancel_token=ctx.cancel_token,
                        request_id=ctx.request_id,
                        provider=ctx.provider,
                    )
                if clarification_question:
                    return clarification_question
                return "".join(collected_tokens) or "(No answer produced)"

            initial_search_context = ""
            if ctx.enable_search and not ctx.cancel_token.cancelled:
                initial_search_context, _ = self._deps.search_service.search_with_events(
                    message,
                    lambda _evt: None,
                    cancel_token=ctx.cancel_token,
                )
            normalized_images = normalize_media_data_urls(images)
            messages = build_messages(ctx.resolved_model, message, history, initial_search_context, normalized_images)
            with proxy_env_guard():
                log_llm_send(
                    rid=ctx.request_id,
                    model=ctx.resolved_model,
                    provider=ctx.provider,
                    messages=messages,
                    thinking=ctx.thinking_mode,
                )
                started = time.monotonic()
                response = client.invoke(messages, **stream_or_invoke_kwargs(ctx.resolved_model, ctx.thinking_mode))
            log_llm_recv(
                rid=ctx.request_id,
                model=ctx.resolved_model,
                provider=ctx.provider,
                response=response,
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
            return extract_text(getattr(response, "content", ""))
        finally:
            log_request_lifecycle(rid=ctx.request_id, model=ctx.resolved_model, evt="once_done")
            self._deps.registry.finish(request_id, token)


class StreamChatUseCase:
    def __init__(self, deps: ChatUseCaseDependencies):
        self._deps = deps

    def execute(
        self,
        *,
        api_key: str,
        message: str,
        history: list,
        model: str | None,
        enable_search: bool,
        agent_mode: bool | None,
        thinking_mode: bool,
        images: list[str] | None,
        request_id: str,
    ) -> SseEventStream:
        resolved_model = self._deps.resolve_model(model)
        token = self._deps.registry.register(request_id, kind="stream")
        ctx = ChatExecutionContext(
            request_id=request_id,
            resolved_model=resolved_model,
            provider=catalog.get_provider(resolved_model),
            protocol=catalog.get_protocol(resolved_model),
            thinking_mode=thinking_mode,
            agent_mode=agent_mode,
            enable_search=enable_search,
            cancel_token=token,
        )
        sink = EventSink(cancel_token=token)
        worker = threading.Thread(
            target=self._produce_events,
            kwargs={
                "sink": sink,
                "ctx": ctx,
                "api_key": api_key,
                "message": message,
                "history": history,
                "images": images,
            },
            daemon=True,
        )
        worker.start()
        return SseEventStream(sink, cancel_token=token)

    def _produce_events(self, *, sink: EventSink, ctx: ChatExecutionContext, api_key: str, message: str, history: list, images):
        log_request_lifecycle(
            rid=ctx.request_id, model=ctx.resolved_model, evt="stream_start",
            agent_mode=ctx.agent_mode, thinking=ctx.thinking_mode,
        )
        try:
            client = self._deps.build_chat_model(
                api_key,
                ctx.resolved_model,
                thinking_mode=ctx.thinking_mode,
            )
            if should_use_agentic_flow(ctx.resolved_model, ctx.agent_mode):
                terminal_seen = False
                for event in stream_agentic(
                    client=client,
                    model=ctx.resolved_model,
                    message=message,
                    history=history,
                    thinking_mode=ctx.thinking_mode,
                    emit_reasoning=catalog.supports(ctx.resolved_model, "thinking") and bool(ctx.thinking_mode),
                    run_web_search=self._deps.search_service.raw_search,
                    run_agent=self._deps.run_agent,
                    cancel_token=ctx.cancel_token,
                    event_sink=sink,
                    request_id=ctx.request_id,
                    provider=ctx.provider,
                ):
                    if event.get("type") == "done":
                        terminal_seen = True
                    if ctx.cancel_token.cancelled and event.get("type") != "done":
                        break
                    sink.emit(event)
                if ctx.cancel_token.cancelled and not terminal_seen:
                    sink.emit({"type": "done", "finish_reason": "stop"})
                return

            event_buffer: list[dict] = []
            initial_search_context = ""
            if ctx.enable_search and not ctx.cancel_token.cancelled:
                initial_search_context, _ = self._deps.search_service.search_with_events(
                    message,
                    event_buffer.append,
                    cancel_token=ctx.cancel_token,
                )
                for event in event_buffer:
                    sink.emit(event)
            normalized_images = normalize_media_data_urls(images)
            messages = build_messages(ctx.resolved_model, message, history, initial_search_context, normalized_images)
            terminal_seen = False
            for event in stream_direct(
                client=client,
                model=ctx.resolved_model,
                messages=messages,
                thinking_mode=ctx.thinking_mode,
                emit_reasoning=catalog.supports(ctx.resolved_model, "thinking") and bool(ctx.thinking_mode),
                cancel_token=ctx.cancel_token,
                request_id=ctx.request_id,
                provider=ctx.provider,
            ):
                if event.get("type") == "done":
                    terminal_seen = True
                if ctx.cancel_token.cancelled and event.get("type") != "done":
                    break
                sink.emit(event)
            if ctx.cancel_token.cancelled and not terminal_seen:
                sink.emit({"type": "done", "finish_reason": "stop"})
        except Exception as exc:  # noqa: BLE001
            if not ctx.cancel_token.cancelled:
                sink.emit({"type": "error", "error": str(exc)})
                sink.emit({"type": "done", "finish_reason": "error"})
        finally:
            log_request_lifecycle(rid=ctx.request_id, model=ctx.resolved_model, evt="stream_done")
            self._deps.registry.finish(ctx.request_id, ctx.cancel_token)
            sink.close()


class CancelChatUseCase:
    def __init__(self, registry: CancellationRegistry):
        self._registry = registry

    def execute(self, request_id: str) -> dict:
        cancelled = self._registry.cancel(request_id)
        if cancelled:
            return {"cancelled": True}
        return {"cancelled": False, "reason": "request_not_found"}

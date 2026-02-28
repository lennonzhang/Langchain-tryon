"""Tool-calling agent orchestration using LangChain."""

from __future__ import annotations

from .message_builder import history_as_messages
from .model_profile import stream_or_invoke_kwargs

_AGENT_MAX_STEPS = 3


def run_agent(
    client,
    model: str,
    message: str,
    history: list,
    thinking_mode: bool,
    search_provider,
    event_collector: list[dict] | None = None,
    event_emitter=None,
    emit_reasoning: bool = False,
) -> str:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.prompts import ChatPromptTemplate
    from .tools_registry import build_agent_tools

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

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a helpful assistant that can use tools to find information. "
         "Answer in the same language as the user's question."),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    # Tool-calling agents use structured API calls instead of text parsing,
    # so thinking mode can remain enabled without breaking the agent loop.
    llm = client.bind(**stream_or_invoke_kwargs(model, thinking_mode))
    tools = build_agent_tools(search_provider=search_provider)
    agent = create_tool_calling_agent(llm, tools, prompt)
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
            "chat_history": history_as_messages(history),
        },
        config={"callbacks": callbacks},
    )
    output = result.get("output", "")
    return output.strip() if isinstance(output, str) else str(output)

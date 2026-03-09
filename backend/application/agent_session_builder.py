from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage


def build_agent_initial_messages(system_prompt: str, history_messages: list, message: str) -> list:
    history_systems = [
        msg.content
        for msg in history_messages
        if isinstance(msg, SystemMessage) and isinstance(msg.content, str) and msg.content.strip()
    ]
    non_system_history = [msg for msg in history_messages if not isinstance(msg, SystemMessage)]

    merged_system_prompt = system_prompt
    if history_systems:
        merged_system_prompt += "\n\n" + "\n\n".join(history_systems)

    initial_messages = [SystemMessage(content=merged_system_prompt)]
    initial_messages.extend(non_system_history)
    initial_messages.append(HumanMessage(content=message))
    return initial_messages

from __future__ import annotations


def build_agent_tools(*, search_provider):
    """Build LangChain tools for the tool-calling agent.

    ``search_provider`` is a :class:`SearchProvider` instance that handles
    event emission internally, so the tool only needs to call
    ``search_with_events``.
    """
    from langchain_core.tools import tool

    @tool("web_search")
    def web_search_tool(query: str) -> str:
        """Search the web for up-to-date information."""
        context, _results = search_provider.search_with_events(query)
        return context or "No useful search results."

    return [web_search_tool]

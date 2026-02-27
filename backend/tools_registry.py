def build_react_tools(*, run_web_search, emit_event):
    from langchain_core.tools import tool

    @tool("web_search")
    def web_search_tool(query: str) -> str:
        """Search the web for up-to-date information."""
        emit_event({"type": "search_start", "query": query})
        try:
            context, results = run_web_search(query)
            emit_event({"type": "search_done", "results": results})
            return context or "No useful search results."
        except Exception as exc:  # noqa: BLE001
            emit_event({"type": "search_error", "error": str(exc)})
            return f"Search error: {exc}"

    return [web_search_tool]

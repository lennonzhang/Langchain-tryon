"""Agent tool definitions — modular registry with conditional selection."""

from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)


# ── individual tool builders ────────────────────────────────────

def _build_web_search_tool(search_provider):
    from langchain_core.tools import tool

    @tool("web_search")
    def web_search_tool(query: str) -> str:
        """Search the web for up-to-date information."""
        context, _results = search_provider.search_with_events(query)
        return context or "No useful search results."

    return web_search_tool


def _build_read_url_tool():
    from langchain_core.tools import tool

    @tool("read_url")
    def read_url_tool(url: str) -> str:
        """Fetch and read the content of a specific web page URL.

        Use this tool when you need to read the full content of a page
        found via web_search, or any URL provided by the user.
        """
        from .web_search import load_webpage_content

        content = load_webpage_content(url, max_chars=4000)
        return content or "Could not load page content."

    return read_url_tool


def _build_python_exec_tool():
    import subprocess
    import tempfile
    from langchain_core.tools import tool

    _MAX_OUTPUT = 4000
    _TIMEOUT = 15

    @tool("python_exec")
    def python_exec_tool(code: str) -> str:
        """Execute Python code and return stdout/stderr.

        Use this for calculations, data processing, or any task that
        benefits from running code.  The code runs in an isolated process
        with a 15-second timeout.
        """
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8",
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            output = result.stdout
            if result.stderr:
                output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
            output = (output or "(No output)").strip()
            return output[:_MAX_OUTPUT]
        except subprocess.TimeoutExpired:
            return f"Execution timed out after {_TIMEOUT}s."
        except Exception as exc:  # noqa: BLE001
            return f"Execution error: {exc}"
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return python_exec_tool


# ── public builder ──────────────────────────────────────────────

def build_agent_tools(
    *,
    search_provider=None,
    event_emitter: Callable | None = None,
    enabled_tools: set[str] | None = None,
) -> list:
    """Build LangChain tools for the agent.

    Parameters
    ----------
    search_provider:
        Required if ``"web_search"`` is in *enabled_tools*.
    event_emitter:
        Callback for tool-level events (reserved for future use).
    enabled_tools:
        Which tools to include.  ``None`` means all available.
    """
    available: dict = {}

    if search_provider is not None:
        available["web_search"] = _build_web_search_tool(search_provider)

    available["read_url"] = _build_read_url_tool()

    if os.environ.get("ENABLE_CODE_INTERPRETER", "").strip() == "1":
        available["python_exec"] = _build_python_exec_tool()

    if enabled_tools is None:
        return list(available.values())

    return [t for name, t in available.items() if name in enabled_tools]

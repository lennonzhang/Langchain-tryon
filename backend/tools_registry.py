"""Agent tool definitions — modular registry with conditional selection."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MAX_USER_INPUT_OPTIONS = 3
_MAX_QUESTION_LENGTH = 500


class ClarificationOption(BaseModel):
    id: str | None = None
    label: str
    description: str | None = None


class RequestUserInputArgs(BaseModel):
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)
    allow_free_text: bool = True


def normalize_request_user_input_args(args: Any) -> dict[str, Any]:
    payload = args if isinstance(args, dict) else {}
    question_raw = str(payload.get("question") or "").strip() or "Please provide the missing information."
    if len(question_raw) > _MAX_QUESTION_LENGTH:
        question = question_raw[:_MAX_QUESTION_LENGTH].rsplit(" ", 1)[0] + "\u2026"
    else:
        question = question_raw

    normalized_options: list[dict[str, str]] = []
    raw_options = payload.get("options")
    if isinstance(raw_options, list):
        for item in raw_options:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            if len(normalized_options) >= _MAX_USER_INPUT_OPTIONS:
                logger.warning("Truncated clarification options beyond max %d", _MAX_USER_INPUT_OPTIONS)
                break
            option: dict[str, str] = {"label": label}
            option_id = str(item.get("id") or "").strip()
            if option_id:
                option["id"] = option_id
            description = str(item.get("description") or "").strip()
            if description:
                option["description"] = description
            normalized_options.append(option)

    return {
        "question": question,
        "options": normalized_options,
        "allow_free_text": bool(payload.get("allow_free_text", True)),
    }


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


def _build_request_user_input_tool():
    from langchain_core.tools import tool

    @tool("request_user_input", args_schema=RequestUserInputArgs)
    def request_user_input_tool(
        question: str,
        options: list[dict[str, Any]] | None = None,
        allow_free_text: bool = True,
    ) -> str:
        """Ask the user for missing information before continuing the task."""
        _ = (question, options, allow_free_text)
        return "User input requested."

    return request_user_input_tool


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
    available["request_user_input"] = _build_request_user_input_tool()

    if os.environ.get("ENABLE_CODE_INTERPRETER", "").strip() == "1":
        available["python_exec"] = _build_python_exec_tool()

    if enabled_tools is None:
        return list(available.values())

    return [t for name, t in available.items() if name in enabled_tools]

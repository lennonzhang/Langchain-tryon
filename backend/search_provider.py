"""Unified search abstraction — single implementation for agent and non-agent paths."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class SearchProvider:
    """Wraps a raw search function and emits SSE-compatible search events.

    Both the agent (tool-calling) path and the direct streaming path use this class
    so that ``search_start``, ``search_done``, and ``search_error`` events
    are emitted from exactly one place.

    Parameters
    ----------
    search_fn:
        ``(query: str) -> (context_str, results_list)`` — the raw search
        implementation (typically ``nvidia_client._run_web_search``).
    emit_fn:
        Callback that receives a dict event, e.g. ``queue.put`` or
        ``list.append``.
    """

    def __init__(
        self,
        search_fn: Callable[[str], tuple[str, list]],
        emit_fn: Callable[[dict], None],
    ):
        self._search = search_fn
        self._emit = emit_fn

    def search_with_events(self, query: str) -> tuple[str, list]:
        """Run search and emit ``search_start`` / ``search_done`` | ``search_error``."""
        self._emit({"type": "search_start", "query": query})
        try:
            context, results = self._search(query)
            self._emit({"type": "search_done", "results": results})
            return context, results
        except Exception as exc:  # noqa: BLE001
            logger.warning("Search failed: %s", exc, exc_info=True)
            self._emit({"type": "search_error", "error": str(exc)})
            return "", []

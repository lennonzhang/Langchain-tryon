import os
import unittest
from unittest.mock import patch

from backend.search_provider import SearchProvider
from backend.tools_registry import build_agent_tools


class TestToolsRegistry(unittest.TestCase):
    def test_build_agent_tools_search_success_emits_events(self):
        events = []

        def _run_web_search(query):
            self.assertEqual(query, "q")
            return "ctx", [{"title": "r1"}]

        provider = SearchProvider(_run_web_search, events.append)
        tools = build_agent_tools(search_provider=provider)
        # web_search + read_url (python_exec disabled by default)
        self.assertGreaterEqual(len(tools), 2)

        web_search = next(t for t in tools if t.name == "web_search")
        result = web_search.invoke("q")
        self.assertEqual(result, "ctx")
        self.assertEqual(events[0], {"type": "search_start", "query": "q"})
        self.assertEqual(events[1], {"type": "search_done", "results": [{"title": "r1"}]})

    def test_build_agent_tools_search_error_emits_event_and_returns_message(self):
        events = []

        def _run_web_search(_query):
            raise RuntimeError("boom")

        provider = SearchProvider(_run_web_search, events.append)
        tools = build_agent_tools(search_provider=provider)
        web_search = next(t for t in tools if t.name == "web_search")
        result = web_search.invoke("q")

        self.assertIn("No useful search results", result)
        self.assertEqual(events[0], {"type": "search_start", "query": "q"})
        self.assertEqual(events[1], {"type": "search_error", "error": "boom"})

    def test_read_url_tool_present(self):
        tools = build_agent_tools(search_provider=None)
        names = [t.name for t in tools]
        self.assertIn("read_url", names)

    def test_read_url_tool_calls_load_webpage(self):
        tools = build_agent_tools(search_provider=None)
        read_url = next(t for t in tools if t.name == "read_url")
        with patch("backend.web_search.load_webpage_content", return_value="page text"):
            result = read_url.invoke("https://example.com")
        self.assertEqual(result, "page text")

    def test_read_url_tool_returns_fallback_on_empty(self):
        tools = build_agent_tools(search_provider=None)
        read_url = next(t for t in tools if t.name == "read_url")
        with patch("backend.web_search.load_webpage_content", return_value=""):
            result = read_url.invoke("https://example.com")
        self.assertIn("Could not load", result)

    def test_python_exec_disabled_by_default(self):
        tools = build_agent_tools(search_provider=None)
        names = [t.name for t in tools]
        self.assertNotIn("python_exec", names)

    def test_python_exec_enabled_via_env(self):
        with patch.dict(os.environ, {"ENABLE_CODE_INTERPRETER": "1"}):
            tools = build_agent_tools(search_provider=None)
        names = [t.name for t in tools]
        self.assertIn("python_exec", names)

    def test_enabled_tools_filter(self):
        events = []
        provider = SearchProvider(lambda q: ("ctx", []), events.append)
        tools = build_agent_tools(
            search_provider=provider,
            enabled_tools={"web_search"},
        )
        names = [t.name for t in tools]
        self.assertEqual(names, ["web_search"])

    def test_enabled_tools_filter_read_url_only(self):
        tools = build_agent_tools(
            search_provider=None,
            enabled_tools={"read_url"},
        )
        names = [t.name for t in tools]
        self.assertEqual(names, ["read_url"])

    def test_no_search_provider_excludes_web_search(self):
        tools = build_agent_tools(search_provider=None)
        names = [t.name for t in tools]
        self.assertNotIn("web_search", names)
        self.assertIn("read_url", names)


if __name__ == "__main__":
    unittest.main()

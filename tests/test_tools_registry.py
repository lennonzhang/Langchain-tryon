import unittest

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
        self.assertEqual(len(tools), 1)

        result = tools[0].invoke("q")
        self.assertEqual(result, "ctx")
        self.assertEqual(events[0], {"type": "search_start", "query": "q"})
        self.assertEqual(events[1], {"type": "search_done", "results": [{"title": "r1"}]})

    def test_build_agent_tools_search_error_emits_event_and_returns_message(self):
        events = []

        def _run_web_search(_query):
            raise RuntimeError("boom")

        provider = SearchProvider(_run_web_search, events.append)
        tools = build_agent_tools(search_provider=provider)
        result = tools[0].invoke("q")

        self.assertIn("No useful search results", result)
        self.assertEqual(events[0], {"type": "search_start", "query": "q"})
        self.assertEqual(events[1], {"type": "search_error", "error": "boom"})


if __name__ == "__main__":
    unittest.main()

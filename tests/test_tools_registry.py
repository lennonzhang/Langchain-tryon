import unittest

from backend.tools_registry import build_react_tools


class TestToolsRegistry(unittest.TestCase):
    def test_build_react_tools_search_success_emits_events(self):
        events = []

        def _run_web_search(query):
            self.assertEqual(query, "q")
            return "ctx", [{"title": "r1"}]

        tools = build_react_tools(run_web_search=_run_web_search, emit_event=events.append)
        self.assertEqual(len(tools), 1)

        result = tools[0].invoke("q")
        self.assertEqual(result, "ctx")
        self.assertEqual(events[0], {"type": "search_start", "query": "q"})
        self.assertEqual(events[1], {"type": "search_done", "results": [{"title": "r1"}]})

    def test_build_react_tools_search_error_emits_event_and_returns_message(self):
        events = []

        def _run_web_search(_query):
            raise RuntimeError("boom")

        tools = build_react_tools(run_web_search=_run_web_search, emit_event=events.append)
        result = tools[0].invoke("q")

        self.assertIn("Search error: boom", result)
        self.assertEqual(events[0], {"type": "search_start", "query": "q"})
        self.assertEqual(events[1], {"type": "search_error", "error": "boom"})


if __name__ == "__main__":
    unittest.main()

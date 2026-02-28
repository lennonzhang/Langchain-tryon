import unittest

from backend.search_provider import SearchProvider


class TestSearchProvider(unittest.TestCase):
    def test_search_with_events_success(self):
        events = []

        def fake_search(query):
            return "context text", [{"title": "Result 1"}]

        provider = SearchProvider(fake_search, events.append)
        context, results = provider.search_with_events("test query")

        self.assertEqual(context, "context text")
        self.assertEqual(results, [{"title": "Result 1"}])
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0], {"type": "search_start", "query": "test query"})
        self.assertEqual(events[1], {"type": "search_done", "results": [{"title": "Result 1"}]})

    def test_search_with_events_error(self):
        events = []

        def failing_search(_query):
            raise RuntimeError("network error")

        provider = SearchProvider(failing_search, events.append)
        context, results = provider.search_with_events("test query")

        self.assertEqual(context, "")
        self.assertEqual(results, [])
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0], {"type": "search_start", "query": "test query"})
        self.assertEqual(events[1], {"type": "search_error", "error": "network error"})

    def test_search_with_events_empty_results(self):
        events = []

        def empty_search(_query):
            return "", []

        provider = SearchProvider(empty_search, events.append)
        context, results = provider.search_with_events("q")

        self.assertEqual(context, "")
        self.assertEqual(results, [])
        self.assertEqual(events[1], {"type": "search_done", "results": []})


if __name__ == "__main__":
    unittest.main()

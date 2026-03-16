import os
import unittest
from unittest.mock import Mock, patch

from backend.web_search import format_search_context, load_webpage_content, web_search


class TestLoadWebpageContent(unittest.TestCase):
    def test_load_webpage_content_uses_tavily_extract_by_default(self):
        client = Mock()
        client.extract.return_value = {"https://example.com": "Hello world"}

        with patch("backend.web_search.TavilyClient", return_value=client):
            content = load_webpage_content("https://example.com", max_chars=200)

        self.assertEqual(content, "Hello world")
        client.extract.assert_called_once_with(["https://example.com"], timeout_seconds=15.0)

    def test_load_webpage_content_uses_tavily_timeout_env_by_default(self):
        client = Mock()
        client.extract.return_value = {"https://example.com": "Hello world"}

        with (
            patch.dict(os.environ, {"TAVILY_TIMEOUT_SECONDS": "22.5"}, clear=False),
            patch("backend.web_search.TavilyClient", return_value=client),
        ):
            load_webpage_content("https://example.com", max_chars=200)

        client.extract.assert_called_once_with(["https://example.com"], timeout_seconds=22.5)

    def test_load_webpage_content_uses_legacy_when_backend_is_legacy(self):
        with (
            patch.dict(
                os.environ,
                {"SEARCH_BACKEND": "legacy", "WEB_LOADER_TIMEOUT_SECONDS": "7.5"},
                clear=False,
            ),
            patch("backend.web_search._legacy_load_webpage_content", return_value="legacy text") as legacy_mock,
        ):
            content = load_webpage_content("https://example.com", max_chars=200)

        self.assertEqual(content, "legacy text")
        legacy_mock.assert_called_once_with("https://example.com", max_chars=200, timeout_s=7.5)

    def test_load_webpage_content_returns_empty_when_extract_has_no_text(self):
        client = Mock()
        client.extract.return_value = {}

        with patch("backend.web_search.TavilyClient", return_value=client):
            content = load_webpage_content("https://example.com", max_chars=200)

        self.assertEqual(content, "")


class TestWebSearch(unittest.TestCase):
    def test_web_search_maps_tavily_results_and_extracts_content(self):
        client = Mock()
        client.search.return_value = [
            {
                "title": "T1",
                "url": "https://a",
                "snippet": "S1",
                "source_domain": "a",
                "score": 0.9,
            }
        ]
        client.extract.return_value = {"https://a": "page text"}

        with patch("backend.web_search.TavilyClient", return_value=client):
            results = web_search("hello", num_results=3)

        self.assertEqual(
            results,
            [
                {
                    "title": "T1",
                    "url": "https://a",
                    "snippet": "S1",
                    "source_domain": "a",
                    "score": 0.9,
                    "content": "page text",
                }
            ],
        )
        client.search.assert_called_once_with("hello", max_results=3, timeout_seconds=15.0)
        client.extract.assert_called_once_with(["https://a"], timeout_seconds=15.0)

    def test_web_search_skips_extract_when_include_page_content_is_false(self):
        client = Mock()
        client.search.return_value = [
            {
                "title": "T1",
                "url": "https://a",
                "snippet": "S1",
                "source_domain": "a",
            }
        ]

        with patch("backend.web_search.TavilyClient", return_value=client):
            results = web_search("hello", include_page_content=False)

        self.assertEqual(results[0]["title"], "T1")
        client.extract.assert_not_called()

    def test_web_search_respects_max_pages_for_extract(self):
        client = Mock()
        client.search.return_value = [
            {"title": "T1", "url": "https://a1", "snippet": "S1", "source_domain": "a1"},
            {"title": "T2", "url": "https://a2", "snippet": "S2", "source_domain": "a2"},
            {"title": "T3", "url": "https://a3", "snippet": "S3", "source_domain": "a3"},
        ]
        client.extract.return_value = {"https://a1": "page1", "https://a2": "page2"}

        with patch("backend.web_search.TavilyClient", return_value=client):
            results = web_search("hello", num_results=3, max_pages=2, concurrency=2)

        self.assertIn("content", results[0])
        self.assertIn("content", results[1])
        self.assertNotIn("content", results[2])
        client.extract.assert_called_once_with(["https://a1", "https://a2"], timeout_seconds=15.0)

    def test_web_search_dedupes_urls_before_extract(self):
        client = Mock()
        client.search.return_value = [
            {"title": "T1", "url": "https://same", "snippet": "S1", "source_domain": "same"},
            {"title": "T2", "url": "https://same", "snippet": "S2", "source_domain": "same"},
            {"title": "T3", "url": "https://other", "snippet": "S3", "source_domain": "other"},
        ]
        client.extract.return_value = {"https://same": "same text", "https://other": "other text"}

        with patch("backend.web_search.TavilyClient", return_value=client):
            results = web_search("hello", num_results=3, max_pages=3)

        client.extract.assert_called_once_with(["https://same", "https://other"], timeout_seconds=15.0)
        self.assertEqual(results[0]["content"], "same text")
        self.assertEqual(results[2]["content"], "other text")

    def test_web_search_extract_failure_returns_search_only_results(self):
        client = Mock()
        client.search.return_value = [
            {"title": "T1", "url": "https://a", "snippet": "S1", "source_domain": "a"}
        ]
        client.extract.side_effect = RuntimeError("extract boom")

        with patch("backend.web_search.TavilyClient", return_value=client):
            results = web_search("hello", num_results=3)

        self.assertEqual(
            results,
            [{"title": "T1", "url": "https://a", "snippet": "S1", "source_domain": "a"}],
        )

    def test_web_search_raises_when_tavily_search_fails(self):
        client = Mock()
        client.search.side_effect = RuntimeError("boom")

        with (
            patch("backend.web_search.TavilyClient", return_value=client),
            self.assertRaisesRegex(RuntimeError, "boom"),
        ):
            web_search("hello", num_results=3)

    def test_web_search_uses_legacy_when_backend_is_legacy(self):
        with (
            patch.dict(os.environ, {"SEARCH_BACKEND": "legacy"}, clear=False),
            patch("backend.web_search._legacy_web_search", return_value=[{"title": "legacy"}]) as legacy_mock,
        ):
            results = web_search("hello", num_results=3, max_pages=2, concurrency=2)

        self.assertEqual(results, [{"title": "legacy"}])
        legacy_mock.assert_called_once_with(
            "hello",
            num_results=3,
            include_page_content=True,
            page_timeout_s=None,
            total_budget_s=None,
            max_pages=2,
            concurrency=2,
        )

    def test_web_search_prefers_explicit_timeouts(self):
        client = Mock()
        client.search.return_value = []

        with patch("backend.web_search.TavilyClient", return_value=client):
            web_search("hello", page_timeout_s=2.5, total_budget_s=5.5)

        client.search.assert_called_once_with("hello", max_results=5, timeout_seconds=5.5)


class TestFormatSearchContext(unittest.TestCase):
    def test_format_search_context_compact_citation_format(self):
        context = format_search_context(
            "nvidia",
            [
                {
                    "title": "NVIDIA",
                    "url": "https://nvidia.com",
                    "source_domain": "nvidia.com",
                    "snippet": "GPU company",
                    "content": "NVIDIA builds chips.",
                }
            ],
        )
        self.assertIn('search results for "nvidia"', context)
        self.assertIn("[1] NVIDIA", context)
        self.assertIn("Source: nvidia.com", context)
        self.assertIn("URL: https://nvidia.com", context)
        self.assertIn("Summary: GPU company", context)
        self.assertIn("Evidence: NVIDIA builds chips.", context)
        self.assertIn("cite it with [N]", context)

    def test_format_search_context_does_not_claim_tavily_for_legacy_results(self):
        with patch.dict(os.environ, {"SEARCH_BACKEND": "legacy"}, clear=False):
            context = format_search_context(
                "legacy query",
                [{"title": "Legacy", "url": "https://example.com", "snippet": "snippet"}],
            )

        self.assertIn('search results for "legacy query"', context)
        self.assertNotIn("Tavily results", context)

    def test_format_search_context_caps_total_length(self):
        long_text = "x" * 2000
        context = format_search_context(
            "query",
            [
                {
                    "title": "Title",
                    "url": "https://a",
                    "source_domain": "a",
                    "snippet": long_text,
                    "content": long_text,
                }
            ]
            * 10,
        )
        self.assertLessEqual(len(context), 3200)


if __name__ == "__main__":
    unittest.main()

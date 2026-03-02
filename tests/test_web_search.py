import sys
import types
import unittest
import time
from unittest.mock import patch

import requests

from backend.web_search import format_search_context, load_webpage_content, web_search


class TestWebSearch(unittest.TestCase):
    def test_load_webpage_content_falls_back_to_requests(self):
        class BrokenLoader:
            def __init__(self, *args, **kwargs):
                pass

            def load(self):
                raise RuntimeError("timeout")

        class FakeResp:
            text = "<html><body><h1>Title</h1><p>Hello world</p></body></html>"

            def raise_for_status(self):
                return None

        pkg = types.ModuleType("langchain_community")
        mod = types.ModuleType("langchain_community.document_loaders")
        mod.WebBaseLoader = BrokenLoader
        pkg.document_loaders = mod

        with (
            patch.dict(
                sys.modules,
                {
                    "langchain_community": pkg,
                    "langchain_community.document_loaders": mod,
                },
            ),
            patch("backend.web_search.requests.get", return_value=FakeResp()) as get_mock,
        ):
            content = load_webpage_content("https://example.com", max_chars=200)

        self.assertIn("Title", content)
        self.assertIn("Hello world", content)
        get_mock.assert_called_once()

    def test_load_webpage_content_ssl_error_retries_insecure(self):
        class BrokenLoader:
            def __init__(self, *args, **kwargs):
                pass

            def load(self):
                raise RuntimeError("loader fail")

        class FakeResp:
            text = "<html><body>ok body</body></html>"

            def raise_for_status(self):
                return None

        pkg = types.ModuleType("langchain_community")
        mod = types.ModuleType("langchain_community.document_loaders")
        mod.WebBaseLoader = BrokenLoader
        pkg.document_loaders = mod

        with (
            patch.dict(
                sys.modules,
                {
                    "langchain_community": pkg,
                    "langchain_community.document_loaders": mod,
                },
            ),
            patch(
                "backend.web_search.requests.get",
                side_effect=[requests.exceptions.SSLError("bad cert"), FakeResp()],
            ) as get_mock,
        ):
            content = load_webpage_content("https://example.com", max_chars=200)

        self.assertIn("ok body", content)
        self.assertEqual(get_mock.call_count, 2)
        self.assertFalse(get_mock.call_args_list[0].kwargs.get("verify", True) is False)
        self.assertEqual(get_mock.call_args_list[1].kwargs.get("verify"), False)

    def test_web_search_maps_ddg_fields(self):
        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                self.query = query
                self.max_results = max_results
                return [{"title": "T1", "href": "https://a", "body": "S1"}]

        fake_module = types.ModuleType("duckduckgo_search")
        fake_module.DDGS = FakeDDGS

        with (
            patch.dict(sys.modules, {"duckduckgo_search": fake_module}),
            patch("backend.web_search.load_webpage_content", return_value="page text"),
        ):
            results = web_search("hello", num_results=3)

        self.assertEqual(
            results,
            [{"title": "T1", "url": "https://a", "snippet": "S1", "content": "page text"}],
        )

    def test_web_search_returns_empty_on_runtime_error(self):
        class BrokenDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                raise RuntimeError("boom")

        fake_module = types.ModuleType("duckduckgo_search")
        fake_module.DDGS = BrokenDDGS

        with patch.dict(sys.modules, {"duckduckgo_search": fake_module}):
            results = web_search("hello", num_results=3)

        self.assertEqual(results, [])

    def test_web_search_respects_max_pages(self):
        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                return [
                    {"title": "T1", "href": "https://a1", "body": "S1"},
                    {"title": "T2", "href": "https://a2", "body": "S2"},
                    {"title": "T3", "href": "https://a3", "body": "S3"},
                ]

        fake_module = types.ModuleType("duckduckgo_search")
        fake_module.DDGS = FakeDDGS

        with (
            patch.dict(sys.modules, {"duckduckgo_search": fake_module}),
            patch("backend.web_search.load_webpage_content", return_value="page text") as load_mock,
        ):
            results = web_search("hello", num_results=3, max_pages=2, concurrency=2)

        self.assertEqual(load_mock.call_count, 2)
        self.assertIn("content", results[0])
        self.assertIn("content", results[1])
        self.assertNotIn("content", results[2])

    def test_web_search_budget_timeout_returns_partial_results(self):
        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                return [
                    {"title": "Slow", "href": "https://slow", "body": "S0"},
                    {"title": "Fast1", "href": "https://fast1", "body": "S1"},
                    {"title": "Fast2", "href": "https://fast2", "body": "S2"},
                ]

        def _fake_loader(url, max_chars=1800, timeout_s=2.0):
            if "slow" in url:
                time.sleep(0.5)
                return "slow content"
            return f"content-{url[-1]}"

        fake_module = types.ModuleType("duckduckgo_search")
        fake_module.DDGS = FakeDDGS

        with (
            patch.dict(sys.modules, {"duckduckgo_search": fake_module}),
            patch("backend.web_search.load_webpage_content", side_effect=_fake_loader),
        ):
            started = time.monotonic()
            results = web_search(
                "hello",
                num_results=3,
                total_budget_s=0.05,
                concurrency=3,
                max_pages=3,
            )
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.3)
        self.assertIn("content", results[1])
        self.assertIn("content", results[2])
        self.assertNotIn("content", results[0])

    def test_web_search_single_page_failure_isolated(self):
        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                return [
                    {"title": "OK", "href": "https://ok", "body": "S1"},
                    {"title": "Bad", "href": "https://bad", "body": "S2"},
                ]

        def _fake_loader(url, max_chars=1800, timeout_s=2.0):
            if "bad" in url:
                raise RuntimeError("boom")
            return "ok content"

        fake_module = types.ModuleType("duckduckgo_search")
        fake_module.DDGS = FakeDDGS

        with (
            patch.dict(sys.modules, {"duckduckgo_search": fake_module}),
            patch("backend.web_search.load_webpage_content", side_effect=_fake_loader),
        ):
            results = web_search("hello", num_results=2, total_budget_s=1.0, concurrency=2)

        self.assertIn("content", results[0])
        self.assertNotIn("content", results[1])

    def test_format_search_context(self):
        context = format_search_context(
            "nvidia",
            [
                {
                    "title": "NVIDIA",
                    "url": "https://nvidia.com",
                    "snippet": "GPU company",
                    "content": "NVIDIA builds chips.",
                }
            ],
        )
        self.assertIn('search results for "nvidia"', context)
        self.assertIn("[1] NVIDIA", context)
        self.assertIn("URL: https://nvidia.com", context)
        self.assertIn("GPU company", context)
        self.assertIn("Page content: NVIDIA builds chips.", context)


if __name__ == "__main__":
    unittest.main()

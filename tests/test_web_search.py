import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import types

import requests

from backend.web_search import format_search_context, load_webpage_content, web_search


class _FakeHTTPXResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class TestLoadWebpageContent(unittest.TestCase):
    @patch("backend.web_search._load_pages_sync")
    def test_load_webpage_content_returns_content(self, mock_sync):
        mock_sync.return_value = {"https://example.com": "Hello world"}
        content = load_webpage_content("https://example.com", max_chars=200)
        self.assertEqual(content, "Hello world")
        mock_sync.assert_called_once()

    @patch("backend.web_search._fetch_with_requests", return_value="fallback text")
    @patch("backend.web_search._load_pages_sync", return_value={})
    def test_load_webpage_content_falls_back_to_requests(self, mock_sync, mock_req):
        content = load_webpage_content("https://example.com", max_chars=200)
        self.assertEqual(content, "fallback text")
        mock_req.assert_called_once()

    @patch("backend.web_search._fetch_with_requests", return_value="fallback text")
    @patch("backend.web_search._load_pages_sync", side_effect=RuntimeError("boom"))
    def test_load_webpage_content_falls_back_on_exception(self, mock_sync, mock_req):
        content = load_webpage_content("https://example.com", max_chars=200)
        self.assertEqual(content, "fallback text")


class TestFetchWithRequests(unittest.TestCase):
    def test_ssl_error_retries_insecure(self):
        class FakeResp:
            text = "<html><body>ok body</body></html>"

            def raise_for_status(self):
                return None

        with patch(
            "backend.web_search.requests.get",
            side_effect=[requests.exceptions.SSLError("bad cert"), FakeResp()],
        ) as get_mock:
            from backend.web_search import _fetch_with_requests

            content = _fetch_with_requests("https://example.com", max_chars=200)

        self.assertIn("ok body", content)
        self.assertEqual(get_mock.call_count, 2)
        self.assertFalse(get_mock.call_args_list[0].kwargs.get("verify", True) is False)
        self.assertEqual(get_mock.call_args_list[1].kwargs.get("verify"), False)


class TestExtractText(unittest.TestCase):
    def test_prefers_trafilatura(self):
        from backend.web_search import _extract_text

        html = "<html><body><nav>Menu</nav><article><p>Main content here.</p></article></body></html>"
        with patch("trafilatura.extract", return_value="Main content here.") as mock_traf:
            result = _extract_text(html, max_chars=200)
        self.assertEqual(result, "Main content here.")
        mock_traf.assert_called_once()

    def test_falls_back_to_bs4(self):
        from backend.web_search import _extract_text

        html = "<html><body><p>Hello world</p></body></html>"
        with patch("trafilatura.extract", return_value=None):
            result = _extract_text(html, max_chars=200)
        self.assertIn("Hello world", result)

    def test_falls_back_on_trafilatura_error(self):
        from backend.web_search import _extract_text

        html = "<html><body><p>Hello world</p></body></html>"
        with patch("trafilatura.extract", side_effect=RuntimeError("boom")):
            result = _extract_text(html, max_chars=200)
        self.assertIn("Hello world", result)


class TestWebSearch(unittest.TestCase):
    def _make_fake_ddgs(self, hits):
        class FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=5):
                return hits

        fake_module = types.ModuleType("duckduckgo_search")
        fake_module.DDGS = FakeDDGS
        return fake_module

    def test_web_search_maps_ddg_fields(self):
        hits = [{"title": "T1", "href": "https://a", "body": "S1"}]
        fake_module = self._make_fake_ddgs(hits)

        with (
            patch.dict("sys.modules", {"duckduckgo_search": fake_module}),
            patch(
                "backend.web_search._load_pages_sync",
                return_value={"https://a": "page text"},
            ),
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

        with patch.dict("sys.modules", {"duckduckgo_search": fake_module}):
            results = web_search("hello", num_results=3)

        self.assertEqual(results, [])

    def test_web_search_respects_max_pages(self):
        hits = [
            {"title": "T1", "href": "https://a1", "body": "S1"},
            {"title": "T2", "href": "https://a2", "body": "S2"},
            {"title": "T3", "href": "https://a3", "body": "S3"},
        ]
        fake_module = self._make_fake_ddgs(hits)

        with (
            patch.dict("sys.modules", {"duckduckgo_search": fake_module}),
            patch(
                "backend.web_search._load_pages_sync",
                return_value={"https://a1": "page1", "https://a2": "page2"},
            ) as load_mock,
        ):
            results = web_search("hello", num_results=3, max_pages=2, concurrency=2)

        load_mock.assert_called_once()
        called_urls = load_mock.call_args.kwargs.get("urls") or load_mock.call_args[0][0]
        self.assertEqual(len(called_urls), 2)
        self.assertIn("content", results[0])
        self.assertIn("content", results[1])
        self.assertNotIn("content", results[2])

    def test_web_search_budget_timeout_returns_partial_results(self):
        hits = [
            {"title": "Slow", "href": "https://slow", "body": "S0"},
            {"title": "Fast1", "href": "https://fast1", "body": "S1"},
            {"title": "Fast2", "href": "https://fast2", "body": "S2"},
        ]
        fake_module = self._make_fake_ddgs(hits)

        def _fake_sync_load(urls, read_timeout, connect_timeout, budget_s, max_chars, concurrency):
            # Simulate: slow URL times out, fast ones succeed
            result = {}
            for url in urls:
                if "slow" not in url:
                    result[url] = f"content-{url[-1]}"
            return result

        with (
            patch.dict("sys.modules", {"duckduckgo_search": fake_module}),
            patch("backend.web_search._load_pages_sync", side_effect=_fake_sync_load),
        ):
            results = web_search(
                "hello",
                num_results=3,
                total_budget_s=0.05,
                concurrency=3,
                max_pages=3,
            )

        self.assertIn("content", results[1])
        self.assertIn("content", results[2])
        self.assertNotIn("content", results[0])

    def test_web_search_single_page_failure_isolated(self):
        hits = [
            {"title": "OK", "href": "https://ok", "body": "S1"},
            {"title": "Bad", "href": "https://bad", "body": "S2"},
        ]
        fake_module = self._make_fake_ddgs(hits)

        def _fake_sync_load(urls, read_timeout, connect_timeout, budget_s, max_chars, concurrency):
            return {"https://ok": "ok content"}

        with (
            patch.dict("sys.modules", {"duckduckgo_search": fake_module}),
            patch("backend.web_search._load_pages_sync", side_effect=_fake_sync_load),
        ):
            results = web_search("hello", num_results=2, total_budget_s=1.0, concurrency=2)

        self.assertIn("content", results[0])
        self.assertNotIn("content", results[1])


class TestFormatSearchContext(unittest.TestCase):
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


class TestAsyncPageLoader(unittest.TestCase):
    def test_load_pages_async_concurrent(self):
        """Verify async loader fetches multiple pages concurrently."""
        from backend.web_search import _load_pages_async

        async def _run():
            with patch("httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()

                async def fake_get(url, **kwargs):
                    resp = _FakeHTTPXResponse(text=f"<p>Content for {url}</p>")
                    return resp

                mock_client.get = fake_get
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                with patch("backend.web_search._extract_text", side_effect=lambda html, max_chars: html):
                    result = await _load_pages_async(
                        urls=["https://a.com", "https://b.com"],
                        read_timeout=5.0,
                        connect_timeout=3.0,
                        budget_s=10.0,
                        max_chars=500,
                        concurrency=3,
                    )

            return result

        result = asyncio.run(_run())
        self.assertEqual(len(result), 2)
        self.assertIn("https://a.com", result)
        self.assertIn("https://b.com", result)


if __name__ == "__main__":
    unittest.main()

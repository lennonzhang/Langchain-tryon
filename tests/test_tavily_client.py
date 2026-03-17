import os
import unittest
from unittest.mock import Mock, patch

import httpx

from backend.infrastructure.search.tavily_client import (
    TavilyClient,
    resolve_search_backend,
    resolve_tavily_settings,
)


class TestTavilySettings(unittest.TestCase):
    def test_resolve_search_backend_defaults_to_tavily(self):
        with patch.dict(os.environ, {}, clear=False):
            self.assertEqual(resolve_search_backend(), "tavily")

    def test_resolve_search_backend_accepts_legacy(self):
        with patch.dict(os.environ, {"SEARCH_BACKEND": "legacy"}, clear=False):
            self.assertEqual(resolve_search_backend(), "legacy")

    def test_resolve_tavily_settings_prefers_new_envs(self):
        with patch.dict(
            os.environ,
            {
                "TAVILY_API_KEY": "tvly-k",
                "TAVILY_BASE_URL": "https://api.test",
                "TAVILY_TIMEOUT_SECONDS": "22",
                "TAVILY_SEARCH_DEPTH": "advanced",
                "TAVILY_EXTRACT_DEPTH": "basic",
                "TAVILY_MAX_EXTRACT_RESULTS": "7",
                "WEB_SEARCH_TOTAL_BUDGET_SECONDS": "5",
                "WEB_LOADER_MAX_PAGES": "2",
            },
            clear=False,
        ):
            settings = resolve_tavily_settings()

        self.assertEqual(settings.api_key, "tvly-k")
        self.assertEqual(settings.base_url, "https://api.test")
        self.assertEqual(settings.timeout_seconds, 22.0)
        self.assertEqual(settings.search_depth, "advanced")
        self.assertEqual(settings.extract_depth, "basic")
        self.assertEqual(settings.extract_timeout_seconds, 30.0)
        self.assertEqual(settings.max_extract_results, 7)
        self.assertTrue(settings.ssl_verify)

    def test_resolve_tavily_settings_falls_back_to_legacy_envs(self):
        with patch.dict(
            os.environ,
            {
                "TAVILY_API_KEY": "tvly-k",
                "TAVILY_TIMEOUT_SECONDS": "",
                "TAVILY_EXTRACT_DEPTH": "",
                "TAVILY_MAX_EXTRACT_RESULTS": "",
                "WEB_SEARCH_TOTAL_BUDGET_SECONDS": "5",
                "WEB_LOADER_MAX_PAGES": "2",
            },
            clear=False,
        ):
            settings = resolve_tavily_settings()

        self.assertEqual(settings.timeout_seconds, 5.0)
        self.assertEqual(settings.max_extract_results, 2)
        self.assertEqual(settings.extract_timeout_seconds, 30.0)

    def test_resolve_tavily_settings_reads_extract_timeout_and_ssl_verify(self):
        with patch.dict(
            os.environ,
            {
                "TAVILY_API_KEY": "tvly-k",
                "TAVILY_EXTRACT_TIMEOUT_SECONDS": "45",
                "TAVILY_SSL_VERIFY": "false",
            },
            clear=False,
        ):
            settings = resolve_tavily_settings()

        self.assertEqual(settings.extract_timeout_seconds, 45.0)
        self.assertFalse(settings.ssl_verify)


class TestTavilyClient(unittest.TestCase):
    def test_init_raises_without_api_key(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "Missing TAVILY_API_KEY"):
                TavilyClient()

    def test_extract_empty_urls_returns_empty_dict(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-k"}, clear=False):
            client = TavilyClient()
            self.assertEqual(client.extract([]), {})

    def test_close_closes_underlying_client(self):
        fake_client = Mock()
        fake_client.is_closed = False

        with (
            patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-k"}, clear=False),
            patch("backend.infrastructure.search.tavily_client.httpx.Client", return_value=fake_client),
        ):
            client = TavilyClient()
            # Force client creation
            client._client()
            client.close()

        fake_client.close.assert_called_once()

    def test_close_noop_when_not_created(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-k"}, clear=False):
            client = TavilyClient()
            # Should not raise
            client.close()

    def test_search_normalizes_results(self):
        fake_response = Mock()
        fake_response.json.return_value = {
            "results": [
                {
                    "title": "Title",
                    "url": "https://example.com/path",
                    "content": "summary",
                    "score": 0.42,
                    "published_date": "2026-03-16",
                }
            ]
        }
        fake_response.raise_for_status.return_value = None
        fake_client = Mock()
        fake_client.post.return_value = fake_response
        fake_client.is_closed = False

        with (
            patch.dict(
                os.environ,
                {
                    "TAVILY_API_KEY": "tvly-k",
                    "TAVILY_EXTRACT_DEPTH": "",
                },
                clear=False,
            ),
            patch("backend.infrastructure.search.tavily_client.httpx.Client", return_value=fake_client),
        ):
            client = TavilyClient()
            results = client.search("q")

        self.assertEqual(
            results,
            [
                {
                    "title": "Title",
                    "url": "https://example.com/path",
                    "snippet": "summary",
                    "source_domain": "example.com",
                    "score": 0.42,
                    "published_date": "2026-03-16",
                }
            ],
        )

    def test_extract_returns_url_text_map(self):
        fake_response = Mock()
        fake_response.json.return_value = {
            "results": [
                {"url": "https://a", "raw_content": "hello"},
                {"url": "https://b", "content": "world"},
            ]
        }
        fake_response.raise_for_status.return_value = None
        fake_client = Mock()
        fake_client.post.return_value = fake_response
        fake_client.is_closed = False

        with (
            patch.dict(
                os.environ,
                {
                    "TAVILY_API_KEY": "tvly-k",
                    "TAVILY_EXTRACT_DEPTH": "",
                },
                clear=False,
            ),
            patch("backend.infrastructure.search.tavily_client.httpx.Client", return_value=fake_client),
        ):
            client = TavilyClient()
            results = client.extract(["https://a", "https://b"])

        self.assertEqual(results, {"https://a": "hello", "https://b": "world"})
        post_kwargs = fake_client.post.call_args.kwargs
        self.assertEqual(post_kwargs["json"]["timeout"], 30.0)
        self.assertEqual(post_kwargs["json"]["extract_depth"], "basic")

    def test_extract_uses_ssl_verify_and_explicit_timeouts(self):
        fake_response = Mock()
        fake_response.json.return_value = {"results": [{"url": "https://a", "content": "hello"}]}
        fake_response.raise_for_status.return_value = None
        fake_client = Mock()
        fake_client.post.return_value = fake_response
        fake_client.__enter__ = Mock(return_value=fake_client)
        fake_client.__exit__ = Mock(return_value=False)

        with (
            patch.dict(
                os.environ,
                {
                    "TAVILY_API_KEY": "tvly-k",
                    "TAVILY_SSL_VERIFY": "false",
                },
                clear=False,
            ),
            patch("backend.infrastructure.search.tavily_client.httpx.Client", return_value=fake_client) as client_cls,
        ):
            client = TavilyClient()
            results = client.extract(["https://a"], timeout_seconds=50.0, api_timeout_seconds=40.0)

        self.assertEqual(results, {"https://a": "hello"})
        client_cls.assert_called_once_with(timeout=50.0, verify=False)
        post_kwargs = fake_client.post.call_args.kwargs
        self.assertEqual(post_kwargs["json"]["timeout"], 40.0)

    def test_post_translates_timeout(self):
        fake_client = Mock()
        fake_client.post.side_effect = httpx.TimeoutException("timeout")
        fake_client.is_closed = False

        with (
            patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-k"}, clear=False),
            patch("backend.infrastructure.search.tavily_client.httpx.Client", return_value=fake_client),
        ):
            client = TavilyClient()
            with self.assertRaises(TimeoutError):
                client.search("q")

    def test_post_wraps_invalid_json(self):
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.side_effect = ValueError("not json")
        fake_client = Mock()
        fake_client.post.return_value = fake_response
        fake_client.is_closed = False

        with (
            patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-k"}, clear=False),
            patch("backend.infrastructure.search.tavily_client.httpx.Client", return_value=fake_client),
        ):
            client = TavilyClient()
            with self.assertRaisesRegex(RuntimeError, r"Tavily /search returned invalid JSON\."):
                client.search("q")


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from backend.infrastructure.provider_settings import (
    resolve_openai_sse_read_timeout,
    resolve_provider_settings,
    resolve_provider_timeout,
)


class TestProviderSettings(unittest.TestCase):
    def test_provider_specific_timeout_wins_over_shared_timeout(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_TIMEOUT_SECONDS": "90",
                "MODEL_TIMEOUT_SECONDS": "45",
            },
            clear=False,
        ):
            timeout = resolve_provider_timeout("openai")
        self.assertEqual(timeout, 90.0)

    def test_shared_timeout_used_when_provider_specific_missing(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_TIMEOUT_SECONDS": "",
                "MODEL_TIMEOUT_SECONDS": "45",
            },
            clear=False,
        ):
            timeout = resolve_provider_timeout("openai")
        self.assertEqual(timeout, 45.0)

    def test_disabled_ssl_logs_warning(self):
        with (
            patch.dict(os.environ, {"OPENAI_SSL_VERIFY": "false"}, clear=False),
            patch("backend.infrastructure.provider_settings.logger.warning") as warning_mock,
        ):
            settings = resolve_provider_settings("openai", fallback_api_key="fallback")
        self.assertFalse(settings.ssl_verify)
        warning_mock.assert_called_once()

    def test_openai_sse_read_timeout_uses_env_value(self):
        with patch.dict(os.environ, {"OPENAI_SSE_READ_TIMEOUT_SECONDS": "720"}, clear=False):
            timeout = resolve_openai_sse_read_timeout()
        self.assertEqual(timeout, 720.0)

    def test_openai_sse_read_timeout_defaults_when_missing_or_invalid(self):
        with patch.dict(os.environ, {"OPENAI_SSE_READ_TIMEOUT_SECONDS": ""}, clear=False):
            self.assertEqual(resolve_openai_sse_read_timeout(), 600.0)
        with patch.dict(os.environ, {"OPENAI_SSE_READ_TIMEOUT_SECONDS": "bad"}, clear=False):
            self.assertEqual(resolve_openai_sse_read_timeout(), 600.0)

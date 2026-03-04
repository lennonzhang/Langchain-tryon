import unittest
import os
import sys
import types
from unittest.mock import Mock, patch

from backend.model_profile import build_chat_model
from backend.proxy_chat_model import ProxyGatewayChatModel


class TestModelProfileProviders(unittest.TestCase):
    def test_build_chat_model_nvidia(self):
        fake_module = types.ModuleType("langchain_nvidia_ai_endpoints")
        chat_cls = Mock()
        fake_module.ChatNVIDIA = chat_cls
        with (
            patch.dict(sys.modules, {"langchain_nvidia_ai_endpoints": fake_module}),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "nv-key"}, clear=False),
        ):
            build_chat_model(
                api_key="fallback",
                model="qwen/qwen3.5-397b-a17b",
                thinking_mode=True,
                provider="nvidia",
            )

        kwargs = chat_cls.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "nv-key")
        self.assertEqual(kwargs["model"], "qwen/qwen3.5-397b-a17b")
        self.assertEqual(kwargs["temperature"], 0.6)
        self.assertEqual(kwargs["top_p"], 0.95)

    def test_build_chat_model_anthropic(self):
        with (
            patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "anth-key", "ANTHROPIC_BASE_URL": "https://x.test/api/v1"},
                clear=False,
            ),
        ):
            model = build_chat_model(
                api_key="fallback",
                model="anthropic/claude-sonnet-4-6",
                thinking_mode=True,
                provider="anthropic",
            )

        self.assertIsInstance(model, ProxyGatewayChatModel)
        self.assertEqual(model.provider, "anthropic")
        self.assertEqual(model.model, "claude-sonnet-4-6")
        self.assertEqual(model.api_key, "anth-key")
        self.assertEqual(model.base_url, "https://x.test/api/v1")

    def test_build_chat_model_openai(self):
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "openai-key", "OPENAI_BASE_URL": "https://x.test/api/v1"},
                clear=False,
            ),
        ):
            model = build_chat_model(
                api_key="fallback",
                model="openai/gpt-5.3-codex",
                thinking_mode=True,
                provider="openai",
            )

        self.assertIsInstance(model, ProxyGatewayChatModel)
        self.assertEqual(model.provider, "openai")
        self.assertEqual(model.model, "gpt-5.3-codex")
        self.assertEqual(model.api_key, "openai-key")
        self.assertEqual(model.base_url, "https://x.test/api/v1")
        self.assertTrue(model.thinking_mode)

    def test_build_chat_model_google(self):
        with (
            patch.dict(
                os.environ,
                {"GOOGLE_API_KEY": "gg-key", "GOOGLE_BASE_URL": "https://x.test/api/v1beta"},
                clear=False,
            ),
        ):
            model = build_chat_model(
                api_key="fallback",
                model="google/gemini-3-pro-preview",
                thinking_mode=True,
                provider="google",
            )

        self.assertIsInstance(model, ProxyGatewayChatModel)
        self.assertEqual(model.provider, "google")
        self.assertEqual(model.model, "gemini-3-pro-preview")
        self.assertEqual(model.api_key, "gg-key")
        self.assertEqual(model.base_url, "https://x.test/api/v1beta")

    def test_provider_compat_env_names(self):
        with patch.dict(
            os.environ,
            {
                "CLAUDE_CLIENT_TOKEN_1": "claude-k",
                "CLAUDE_API_URL": "https://claude2.sssaicode.com/api",
                "CODEX_TOKEN_1": "codex-k",
                "CODEX_API_URL": "https://codex2.sssaicode.com/api/v1",
                "GEMINI_API_KEY_1": "gemini-k",
                "GOOGLE_GEMINI_BASE_URL": "https://gemini2.sssaicode.com/api",
            },
            clear=False,
        ):
            claude = build_chat_model(
                api_key="fallback",
                model="anthropic/claude-sonnet-4-6",
                thinking_mode=True,
                provider="anthropic",
            )
            codex = build_chat_model(
                api_key="fallback",
                model="openai/gpt-5.3-codex",
                thinking_mode=True,
                provider="openai",
            )
            gemini = build_chat_model(
                api_key="fallback",
                model="google/gemini-3-pro-preview",
                thinking_mode=True,
                provider="google",
            )

        self.assertEqual(claude.api_key, "claude-k")
        self.assertEqual(claude.base_url, "https://claude2.sssaicode.com/api/v1")
        self.assertEqual(codex.api_key, "codex-k")
        self.assertEqual(codex.base_url, "https://codex2.sssaicode.com/api/v1")
        self.assertEqual(gemini.api_key, "gemini-k")
        self.assertEqual(gemini.base_url, "https://gemini2.sssaicode.com/api/v1beta")


if __name__ == "__main__":
    unittest.main()

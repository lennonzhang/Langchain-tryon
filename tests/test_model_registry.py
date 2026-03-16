import os
import unittest
from unittest.mock import patch

from backend.model_registry import (
    _reset_active,
    capabilities_response,
    get_all,
    get_by_id,
    get_context_window,
    get_default,
    get_ids,
    get_params,
    get_protocol,
    get_provider,
    get_upstream_model,
    supports,
)

_ENV_KEYS = ("NVIDIA_MODELS", "ANTHROPIC_MODELS", "OPENAI_MODELS", "GOOGLE_MODELS")


class TestModelRegistry(unittest.TestCase):
    """Unit tests for backend.model_registry (full registry, no env override)."""

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
        _reset_active()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _reset_active()

    # ── get_all / get_ids ────────────────────────────────────────

    def test_get_all_returns_list(self):
        registry = get_all()
        self.assertIsInstance(registry, list)
        self.assertGreaterEqual(len(registry), 1)

    def test_get_ids_matches_registry(self):
        ids = get_ids()
        self.assertEqual(ids, tuple(m["id"] for m in get_all()))

    def test_known_models_present(self):
        ids = get_ids()
        self.assertIn("moonshotai/kimi-k2.5", ids)
        self.assertIn("qwen/qwen3.5-397b-a17b", ids)
        self.assertIn("qwen/qwen3.5-122b-a10b", ids)
        self.assertIn("z-ai/glm5", ids)
        self.assertIn("anthropic/claude-sonnet-4-6", ids)
        self.assertIn("openai/gpt-5.3-codex", ids)
        self.assertIn("google/gemini-3-pro-preview", ids)

    # ── get_by_id ────────────────────────────────────────────────

    def test_get_by_id_found(self):
        m = get_by_id("moonshotai/kimi-k2.5")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "moonshotai/kimi-k2.5")

    def test_get_by_id_not_found(self):
        self.assertIsNone(get_by_id("unknown/model"))

    # ── get_default ──────────────────────────────────────────────

    def test_get_default_is_codex(self):
        default = get_default()
        self.assertEqual(default["id"], "openai/gpt-5.3-codex")
        self.assertTrue(default["default"])

    def test_exactly_one_default(self):
        defaults = [m for m in get_all() if m["default"]]
        self.assertEqual(len(defaults), 1)

    # ── supports ─────────────────────────────────────────────────

    def test_kimi_capabilities(self):
        self.assertTrue(supports("moonshotai/kimi-k2.5", "thinking"))
        self.assertTrue(supports("moonshotai/kimi-k2.5", "media"))
        self.assertFalse(supports("moonshotai/kimi-k2.5", "agent"))

    def test_qwen_capabilities(self):
        self.assertTrue(supports("qwen/qwen3.5-397b-a17b", "thinking"))
        self.assertFalse(supports("qwen/qwen3.5-397b-a17b", "media"))
        self.assertTrue(supports("qwen/qwen3.5-397b-a17b", "agent"))

    def test_qwen_122b_capabilities(self):
        self.assertTrue(supports("qwen/qwen3.5-122b-a10b", "thinking"))
        self.assertFalse(supports("qwen/qwen3.5-122b-a10b", "media"))
        self.assertTrue(supports("qwen/qwen3.5-122b-a10b", "agent"))

    def test_glm5_capabilities(self):
        self.assertTrue(supports("z-ai/glm5", "thinking"))
        self.assertFalse(supports("z-ai/glm5", "media"))
        self.assertTrue(supports("z-ai/glm5", "agent"))

    def test_gemini_3_pro_capabilities(self):
        self.assertTrue(supports("google/gemini-3-pro-preview", "thinking"))
        self.assertFalse(supports("google/gemini-3-pro-preview", "media"))
        self.assertTrue(supports("google/gemini-3-pro-preview", "agent"))

    def test_unknown_model_supports_nothing(self):
        self.assertFalse(supports("unknown/model", "thinking"))
        self.assertFalse(supports("unknown/model", "media"))
        self.assertFalse(supports("unknown/model", "agent"))

    def test_unknown_capability_returns_false(self):
        self.assertFalse(supports("moonshotai/kimi-k2.5", "nonexistent"))

    # ── get_context_window ───────────────────────────────────────

    def test_known_context_windows(self):
        self.assertEqual(get_context_window("moonshotai/kimi-k2.5"), 131072)
        self.assertEqual(get_context_window("qwen/qwen3.5-397b-a17b"), 128000)
        self.assertEqual(get_context_window("qwen/qwen3.5-122b-a10b"), 262144)
        self.assertEqual(get_context_window("z-ai/glm5"), 128000)

    def test_unknown_model_default_window(self):
        self.assertEqual(get_context_window("unknown/model"), 128000)

    # ── get_params ───────────────────────────────────────────────

    def test_kimi_params(self):
        p = get_params("moonshotai/kimi-k2.5")
        self.assertEqual(p["thinking_control"], "call_time")
        self.assertEqual(p["thinking_kwarg_field"], "thinking")
        self.assertEqual(p["temperature_thinking"], 1.0)
        self.assertEqual(p["temperature_standard"], 0.6)

    def test_qwen_params(self):
        p = get_params("qwen/qwen3.5-397b-a17b")
        self.assertEqual(p["thinking_control"], "call_time")
        self.assertEqual(p["thinking_kwarg_field"], "enable_thinking")
        self.assertEqual(p["top_p"], 0.95)

    def test_qwen_122b_params(self):
        p = get_params("qwen/qwen3.5-122b-a10b")
        self.assertEqual(p["thinking_control"], "call_time")
        self.assertEqual(p["thinking_kwarg_field"], "enable_thinking")
        self.assertEqual(p["top_p"], 0.95)

    def test_glm5_params(self):
        p = get_params("z-ai/glm5")
        self.assertEqual(p["thinking_control"], "construct_time")

    def test_unknown_model_empty_params(self):
        self.assertEqual(get_params("unknown/model"), {})

    def test_get_params_returns_copy(self):
        p1 = get_params("moonshotai/kimi-k2.5")
        p1["temperature_thinking"] = 999
        p2 = get_params("moonshotai/kimi-k2.5")
        self.assertEqual(p2["temperature_thinking"], 1.0)

    def test_provider_metadata(self):
        self.assertEqual(get_provider("moonshotai/kimi-k2.5"), "nvidia")
        self.assertEqual(get_provider("openai/gpt-5.3-codex"), "openai")
        self.assertEqual(get_upstream_model("anthropic/claude-sonnet-4-6"), "claude-sonnet-4-6")
        self.assertEqual(get_protocol("google/gemini-3-pro-preview"), "google_generate_content")

    def test_gemini_3_pro_metadata(self):
        self.assertEqual(get_provider("google/gemini-3-pro-preview"), "google")
        self.assertEqual(get_upstream_model("google/gemini-3-pro-preview"), "gemini-3-pro-preview")
        self.assertEqual(get_protocol("google/gemini-3-pro-preview"), "google_generate_content")
        self.assertEqual(get_context_window("google/gemini-3-pro-preview"), 1048576)

    # ── capabilities_response ────────────────────────────────────

    def test_capabilities_response_shape(self):
        resp = capabilities_response()
        self.assertIn("version", resp)
        self.assertIn("default", resp)
        self.assertIn("models", resp)
        self.assertIsInstance(resp["version"], int)
        self.assertIsInstance(resp["default"], str)
        self.assertIsInstance(resp["models"], list)

    def test_capabilities_response_models_have_required_fields(self):
        resp = capabilities_response()
        for m in resp["models"]:
            self.assertIn("id", m)
            self.assertIn("label", m)
            self.assertIn("capabilities", m)
            self.assertIn("context_window", m)
            caps = m["capabilities"]
            self.assertIn("thinking", caps)
            self.assertIn("media", caps)
            self.assertIn("agent", caps)

    def test_capabilities_response_excludes_params(self):
        resp = capabilities_response()
        for m in resp["models"]:
            self.assertNotIn("params", m)
            self.assertNotIn("default", m)

    def test_capabilities_response_default_matches(self):
        resp = capabilities_response()
        default_id = resp["default"]
        ids = [m["id"] for m in resp["models"]]
        self.assertIn(default_id, ids)


class TestEnvDrivenModels(unittest.TestCase):
    """Tests for *_MODELS env-driven model list."""

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
        _reset_active()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _reset_active()

    # ── fallback when no env set ──────────────────────────────────

    def test_no_env_returns_full_registry(self):
        ids = get_ids()
        self.assertEqual(len(ids), 7)
        self.assertIn("openai/gpt-5.3-codex", ids)

    # ── filtering existing models ─────────────────────────────────

    def test_single_provider_filters_to_listed_models(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6"
        _reset_active()
        ids = get_ids()
        self.assertEqual(ids, ("anthropic/claude-sonnet-4-6",))

    def test_multiple_providers(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6"
        os.environ["OPENAI_MODELS"] = "gpt-5.3-codex"
        _reset_active()
        ids = get_ids()
        self.assertEqual(len(ids), 2)
        self.assertIn("anthropic/claude-sonnet-4-6", ids)
        self.assertIn("openai/gpt-5.3-codex", ids)

    def test_nvidia_models_with_slash_in_name(self):
        os.environ["NVIDIA_MODELS"] = "moonshotai/kimi-k2.5"
        _reset_active()
        ids = get_ids()
        self.assertEqual(ids, ("moonshotai/kimi-k2.5",))

    # ── dynamic model generation ──────────────────────────────────

    def test_dynamic_model_inherits_template(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-opus-4-6-thinking"
        _reset_active()
        m = get_by_id("anthropic/claude-opus-4-6-thinking")
        self.assertIsNotNone(m)
        self.assertEqual(m["provider"], "anthropic")
        self.assertEqual(m["upstream_model"], "claude-opus-4-6-thinking")
        self.assertEqual(m["protocol"], "anthropic_messages")
        self.assertIn("thinking", m["capabilities"])
        self.assertIn("context_window", m)

    def test_dynamic_model_label_is_upstream_name(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6-thinking"
        _reset_active()
        m = get_by_id("anthropic/claude-sonnet-4-6-thinking")
        self.assertEqual(m["label"], "claude-sonnet-4-6-thinking")

    def test_mix_existing_and_dynamic(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6,claude-opus-4-6-thinking"
        _reset_active()
        ids = get_ids()
        self.assertEqual(len(ids), 2)
        # existing keeps original label
        existing = get_by_id("anthropic/claude-sonnet-4-6")
        self.assertEqual(existing["label"], "Claude Sonnet 4.6")
        # dynamic gets upstream name as label
        dynamic = get_by_id("anthropic/claude-opus-4-6-thinking")
        self.assertEqual(dynamic["label"], "claude-opus-4-6-thinking")

    # ── default handling ──────────────────────────────────────────

    def test_default_preserved_when_in_list(self):
        os.environ["OPENAI_MODELS"] = "gpt-5.3-codex"
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6"
        _reset_active()
        default = get_default()
        self.assertEqual(default["id"], "openai/gpt-5.3-codex")

    def test_default_falls_back_to_first_when_original_absent(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6"
        _reset_active()
        default = get_default()
        self.assertEqual(default["id"], "anthropic/claude-sonnet-4-6")
        self.assertTrue(default["default"])

    def test_exactly_one_default(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6,claude-opus-4-6-thinking"
        os.environ["OPENAI_MODELS"] = "gpt-5.3-codex"
        _reset_active()
        defaults = [m for m in get_all() if m["default"]]
        self.assertEqual(len(defaults), 1)

    # ── capabilities_response ─────────────────────────────────────

    def test_capabilities_response_respects_env(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-sonnet-4-6,claude-opus-4-6-thinking"
        _reset_active()
        resp = capabilities_response()
        ids = [m["id"] for m in resp["models"]]
        self.assertEqual(len(ids), 2)
        self.assertIn("anthropic/claude-opus-4-6-thinking", ids)
        self.assertIn(resp["default"], ids)

    def test_capabilities_dynamic_model_has_required_fields(self):
        os.environ["ANTHROPIC_MODELS"] = "claude-opus-4-6-thinking"
        _reset_active()
        resp = capabilities_response()
        m = resp["models"][0]
        for field in ("id", "label", "capabilities", "context_window"):
            self.assertIn(field, m)
        for cap in ("thinking", "media", "agent"):
            self.assertIn(cap, m["capabilities"])

    # ── whitespace / edge cases ───────────────────────────────────

    def test_whitespace_in_env_trimmed(self):
        os.environ["ANTHROPIC_MODELS"] = " claude-sonnet-4-6 , claude-opus-4-6-thinking "
        _reset_active()
        self.assertEqual(len(get_ids()), 2)

    def test_empty_env_value_ignored(self):
        os.environ["ANTHROPIC_MODELS"] = ""
        _reset_active()
        # empty string means not set → full registry fallback
        self.assertEqual(len(get_ids()), 7)

    def test_unknown_provider_model_skipped(self):
        # provider "anthropic" exists, but if we only set an unknown provider env
        # there's no template, so it would be skipped. We test via NVIDIA with
        # a non-existent upstream — it should still generate since nvidia template exists.
        os.environ["NVIDIA_MODELS"] = "fake/nonexistent-model"
        _reset_active()
        ids = get_ids()
        self.assertEqual(len(ids), 1)
        m = get_by_id("nvidia/fake/nonexistent-model")
        self.assertIsNotNone(m)
        self.assertEqual(m["provider"], "nvidia")


    def test_env_file_is_loaded_before_active_catalog_is_built(self):
        def fake_load_env_file(*_args, **_kwargs):
            os.environ["OPENAI_MODELS"] = "gpt-5.4"

        with patch("backend.domain.model_catalog.load_env_file", side_effect=fake_load_env_file) as load_mock:
            _reset_active()
            ids = get_ids()

        self.assertEqual(ids, ("openai/gpt-5.4",))
        load_mock.assert_called()


if __name__ == "__main__":
    unittest.main()

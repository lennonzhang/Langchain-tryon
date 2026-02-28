import unittest

from backend.model_registry import (
    capabilities_response,
    get_all,
    get_by_id,
    get_context_window,
    get_default,
    get_ids,
    get_params,
    supports,
)


class TestModelRegistry(unittest.TestCase):
    """Unit tests for backend.model_registry."""

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
        self.assertIn("z-ai/glm5", ids)

    # ── get_by_id ────────────────────────────────────────────────

    def test_get_by_id_found(self):
        m = get_by_id("moonshotai/kimi-k2.5")
        self.assertIsNotNone(m)
        self.assertEqual(m["id"], "moonshotai/kimi-k2.5")

    def test_get_by_id_not_found(self):
        self.assertIsNone(get_by_id("unknown/model"))

    # ── get_default ──────────────────────────────────────────────

    def test_get_default_is_kimi(self):
        default = get_default()
        self.assertEqual(default["id"], "moonshotai/kimi-k2.5")
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

    def test_glm5_capabilities(self):
        self.assertTrue(supports("z-ai/glm5", "thinking"))
        self.assertFalse(supports("z-ai/glm5", "media"))
        self.assertTrue(supports("z-ai/glm5", "agent"))

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


if __name__ == "__main__":
    unittest.main()

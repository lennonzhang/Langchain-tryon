import unittest

from backend.schemas import ChatRequest, ValidationError


class TestChatRequestFromDict(unittest.TestCase):

    def test_full_payload(self):
        data = {
            "message": "  hello  ",
            "history": [{"role": "user", "content": "hi"}],
            "model": "moonshotai/kimi-k2.5",
            "web_search": True,
            "agent_mode": True,
            "thinking_mode": False,
            "images": ["data:image/png;base64,abc"],
        }
        req = ChatRequest.from_dict(data)
        self.assertEqual(req.message, "hello")
        self.assertEqual(req.history, [{"role": "user", "content": "hi"}])
        self.assertEqual(req.model, "moonshotai/kimi-k2.5")
        self.assertTrue(req.enable_search)
        self.assertTrue(req.agent_mode)
        self.assertFalse(req.thinking_mode)
        self.assertEqual(req.images, ["data:image/png;base64,abc"])
        self.assertIsInstance(req.request_id, str)
        self.assertTrue(len(req.request_id) > 0)

    def test_full_payload_with_request_id(self):
        data = {
            "message": "hello",
            "request_id": "client-123",
        }
        req = ChatRequest.from_dict(data)
        self.assertEqual(req.request_id, "client-123")

    def test_two_requests_get_different_ids(self):
        r1 = ChatRequest.from_dict({"message": "a"})
        r2 = ChatRequest.from_dict({"message": "b"})
        self.assertNotEqual(r1.request_id, r2.request_id)

    def test_missing_message_returns_empty_string(self):
        req = ChatRequest.from_dict({})
        self.assertEqual(req.message, "")

    def test_agent_mode_string_defaults_to_none(self):
        req = ChatRequest.from_dict({"agent_mode": "true"})
        self.assertIsNone(req.agent_mode)

    def test_agent_mode_int_defaults_to_none(self):
        req = ChatRequest.from_dict({"agent_mode": 1})
        self.assertIsNone(req.agent_mode)

    def test_agent_mode_false(self):
        req = ChatRequest.from_dict({"agent_mode": False})
        self.assertFalse(req.agent_mode)

    def test_history_none_returns_empty_list(self):
        req = ChatRequest.from_dict({"history": None})
        self.assertEqual(req.history, [])

    def test_history_string_returns_empty_list(self):
        req = ChatRequest.from_dict({"history": "not a list"})
        self.assertEqual(req.history, [])

    def test_images_non_list_returns_empty_list(self):
        req = ChatRequest.from_dict({"images": 42})
        self.assertEqual(req.images, [])

    def test_thinking_mode_defaults_to_true(self):
        req = ChatRequest.from_dict({})
        self.assertTrue(req.thinking_mode)

    def test_thinking_mode_false(self):
        req = ChatRequest.from_dict({"thinking_mode": False})
        self.assertFalse(req.thinking_mode)

    def test_web_search_truthy_int(self):
        req = ChatRequest.from_dict({"web_search": 1})
        self.assertTrue(req.enable_search)

    def test_web_search_defaults_to_false(self):
        req = ChatRequest.from_dict({})
        self.assertFalse(req.enable_search)

    def test_model_non_string_returns_none(self):
        req = ChatRequest.from_dict({"model": 123})
        self.assertIsNone(req.model)

    def test_model_none_returns_none(self):
        req = ChatRequest.from_dict({"model": None})
        self.assertIsNone(req.model)

    def test_request_id_auto_generated(self):
        req = ChatRequest.from_dict({})
        self.assertIsInstance(req.request_id, str)
        self.assertTrue(len(req.request_id) > 0)

    def test_request_id_preserved_when_provided(self):
        req = ChatRequest.from_dict({"request_id": "my-custom-id"})
        self.assertEqual(req.request_id, "my-custom-id")

    def test_request_id_empty_string_generates_new(self):
        req = ChatRequest.from_dict({"request_id": "  "})
        self.assertNotEqual(req.request_id.strip(), "")

    def test_request_id_non_string_generates_new(self):
        req = ChatRequest.from_dict({"request_id": 123})
        self.assertIsInstance(req.request_id, str)
        self.assertTrue(len(req.request_id) > 0)


    def test_message_too_long_raises_validation_error(self):
        data = {"message": "x" * 100_001}
        with self.assertRaises(ValidationError) as ctx:
            ChatRequest.from_dict(data)
        self.assertIn("message", str(ctx.exception))

    def test_message_at_limit_accepted(self):
        data = {"message": "x" * 100_000}
        req = ChatRequest.from_dict(data)
        self.assertEqual(len(req.message), 100_000)

    def test_history_malformed_items_filtered_out(self):
        data = {
            "message": "hi",
            "history": [
                {"role": "user", "content": "valid"},
                {"invalid": "no role"},
                "not a dict",
                {"role": 123, "content": "bad role type"},
                {"role": "user", "content": 456},
                {"role": "assistant", "content": "also valid"},
            ],
        }
        req = ChatRequest.from_dict(data)
        self.assertEqual(len(req.history), 2)
        self.assertEqual(req.history[0]["content"], "valid")
        self.assertEqual(req.history[1]["content"], "also valid")

    def test_history_capped_at_100(self):
        items = [{"role": "user", "content": f"msg {i}"} for i in range(200)]
        req = ChatRequest.from_dict({"message": "hi", "history": items})
        self.assertLessEqual(len(req.history), 100)

    def test_images_non_string_items_filtered(self):
        data = {"message": "hi", "images": ["valid.png", 123, None, "also_valid.jpg"]}
        req = ChatRequest.from_dict(data)
        self.assertEqual(req.images, ["valid.png", "also_valid.jpg"])

    def test_images_capped_at_10(self):
        data = {"message": "hi", "images": [f"img_{i}" for i in range(20)]}
        req = ChatRequest.from_dict(data)
        self.assertEqual(len(req.images), 10)


if __name__ == "__main__":
    unittest.main()

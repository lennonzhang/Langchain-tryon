import unittest

from backend.provider_event_normalizer import (
    normalize_upstream_error,
    normalized_error_detail,
    parse_error_payload,
)


class TestProviderEventNormalizer(unittest.TestCase):
    def test_parse_error_payload_sonnet(self):
        payload = (
            '{"type":"error","error":{"type":"invalid_request_error","message":"模型配置不存在: "}}'
        )
        err_type, message, rid = parse_error_payload(payload)
        self.assertEqual(err_type, "invalid_request_error")
        self.assertIn("模型配置不存在", message)
        self.assertIsNone(rid)

    def test_parse_error_payload_gemini(self):
        payload = (
            '{"id":"1772509180627-j5rr1jx13eedf","type":"error","error":{"type":"internal_error","message":"服务器错误，请稍后重试"}}'
        )
        err_type, message, rid = parse_error_payload(payload)
        self.assertEqual(err_type, "internal_error")
        self.assertEqual(message, "服务器错误，请稍后重试")
        self.assertEqual(rid, "1772509180627-j5rr1jx13eedf")

    def test_normalize_error_includes_provider_protocol(self):
        payload = (
            '{"type":"error","error":{"type":"invalid_request_error","message":"模型配置不存在: "}}'
        )
        info = normalize_upstream_error(
            "openai/gpt-5.3-codex",
            status=400,
            raw_body=payload,
        )
        detail = normalized_error_detail(info)
        self.assertIn("provider=openai", detail)
        self.assertIn("protocol=openai_responses", detail)
        self.assertIn("status=400", detail)
        self.assertIn("type=invalid_request_error", detail)

    def test_parse_non_json_fallback(self):
        err_type, message, rid = parse_error_payload("timeout")
        self.assertEqual(err_type, "unknown_error")
        self.assertEqual(message, "timeout")
        self.assertIsNone(rid)


if __name__ == "__main__":
    unittest.main()

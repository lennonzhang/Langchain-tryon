import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.gateway import app as gateway_app_module
from backend.gateway.admission import QueueFullError, QueueTimeoutError
from backend.gateway.app import app


class TestGatewayApp(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.state.debug_stream = False
        self._too_long_request_id = "r" * 257

    def test_capabilities_route(self):
        response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("models", body)
        self.assertIn("default", body)

    def test_cancel_route_validates_request_id(self):
        response = self.client.post("/api/chat/cancel", json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "request_id is required")

    def test_cancel_route_rejects_too_long_request_id(self):
        response = self.client.post("/api/chat/cancel", json={"request_id": self._too_long_request_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("request_id: too long", response.json()["error"])

    def test_cancel_route_delegates_to_facade(self):
        with patch("backend.gateway.app.cancel_chat", return_value={"cancelled": True}) as cancel_mock:
            response = self.client.post("/api/chat/cancel", json={"request_id": "rid-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cancelled": True})
        cancel_mock.assert_called_once_with("rid-1")

    def test_cancel_route_rejects_invalid_json(self):
        response = self.client.post(
            "/api/chat/cancel",
            data="{not-json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid JSON body"})

    def test_cancel_route_content_length_precheck_returns_413(self):
        with patch("backend.gateway.app._content_length", return_value=10 * 1024 * 1024 + 1):
            response = self.client.post("/api/chat/cancel", json={"request_id": "rid-precheck"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"error": "Payload too large"})

    def test_cancel_route_returns_not_found_payload(self):
        with patch("backend.gateway.app.cancel_chat", return_value={"cancelled": False, "reason": "request_not_found"}):
            response = self.client.post("/api/chat/cancel", json={"request_id": "rid-missing"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cancelled": False, "reason": "request_not_found"})

    def test_chat_route_returns_503_when_gateway_queue_full(self):
        payload = {"message": "hello", "request_id": "rid-queue-full"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.slot.return_value.__aenter__ = AsyncMock(side_effect=QueueFullError("gateway queue is full"))
            gate.slot.return_value.__aexit__ = AsyncMock(return_value=False)
            response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "gateway queue is full"})

    def test_chat_route_returns_503_when_gateway_queue_times_out(self):
        payload = {"message": "hello", "request_id": "rid-queue-timeout"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.slot.return_value.__aenter__ = AsyncMock(side_effect=QueueTimeoutError("gateway queue timeout"))
            gate.slot.return_value.__aexit__ = AsyncMock(return_value=False)
            response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "gateway queue timeout"})

    def test_chat_route_rejects_too_long_request_id(self):
        response = self.client.post("/api/chat", json={"message": "hello", "request_id": self._too_long_request_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("request_id: too long", response.json()["error"])

    def test_chat_route_content_length_precheck_returns_413(self):
        payload = {"message": "hello", "request_id": "rid-precheck"}
        with patch("backend.gateway.app._content_length", return_value=10 * 1024 * 1024 + 1):
            response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"error": "Payload too large"})

    def test_chat_stream_queue_full_emits_error_and_done(self):
        payload = {"message": "hello", "request_id": "rid-stream-queue-full"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.acquire = AsyncMock(side_effect=QueueFullError("gateway queue is full"))
            response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        body = response.text
        self.assertIn('"type": "error"', body)
        self.assertIn('"error": "gateway queue is full"', body)
        self.assertIn('"type": "done"', body)
        self.assertIn('"finish_reason": "error"', body)
        self.assertIn('"request_id": "rid-stream-queue-full"', body)

    def test_chat_stream_queue_timeout_emits_error_and_done(self):
        payload = {"message": "hello", "request_id": "rid-stream-queue-timeout"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.acquire = AsyncMock(side_effect=QueueTimeoutError("gateway queue timeout"))
            response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('"type": "error"', body)
        self.assertIn('"error": "gateway queue timeout"', body)
        self.assertIn('"type": "done"', body)
        self.assertIn('"finish_reason": "error"', body)
        self.assertIn('"request_id": "rid-stream-queue-timeout"', body)

    def test_chat_stream_rejects_too_long_request_id(self):
        response = self.client.post("/api/chat/stream", json={"message": "hello", "request_id": self._too_long_request_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("request_id: too long", response.json()["error"])

    def test_chat_route_forwards_debug_stream_flag(self):
        payload = {"message": "hello", "request_id": "rid-debug"}
        app.state.debug_stream = True
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.slot.return_value.__aenter__ = AsyncMock(return_value=None)
            gate.slot.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("backend.gateway.app.load_api_key", return_value="test-key"):
                with patch("backend.gateway.app.chat_once", return_value="ok") as chat_once_mock:
                    response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "ok"})
        self.assertTrue(chat_once_mock.call_args.kwargs["debug_stream"])
        self.assertEqual(chat_once_mock.call_args.args[0], "test-key")

    def test_chat_stream_forwards_debug_stream_flag(self):
        payload = {"message": "hello", "request_id": "rid-stream-debug"}
        app.state.debug_stream = True
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.acquire = AsyncMock(return_value=None)
            gate.release = AsyncMock(return_value=None)
            with patch("backend.gateway.app.load_api_key", return_value="test-key"):
                with patch("backend.gateway.app.stream_chat", return_value=iter([{"type": "done", "finish_reason": "stop"}])) as stream_chat_mock:
                    response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(stream_chat_mock.call_args.kwargs["debug_stream"])
        self.assertEqual(stream_chat_mock.call_args.args[0], "test-key")

    def test_chat_route_returns_500_when_api_key_missing(self):
        payload = {"message": "hello", "request_id": "rid-missing-key"}
        with patch("backend.gateway.app.load_api_key", side_effect=RuntimeError("No API key found. Set NVIDIA_API_KEY in system env or .env.")):
            response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "Server misconfigured")
        self.assertIn("No API key found", response.json()["detail"])

    def test_chat_stream_missing_api_key_emits_error_and_done(self):
        payload = {"message": "hello", "request_id": "rid-stream-missing-key"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.acquire = AsyncMock(return_value=None)
            gate.release = AsyncMock(return_value=None)
            with patch("backend.gateway.app.load_api_key", side_effect=RuntimeError("No API key found. Set NVIDIA_API_KEY in system env or .env.")):
                response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('"type": "error"', body)
        self.assertIn('"error": "Server misconfigured: No API key found.', body)
        self.assertIn('"type": "done"', body)
        self.assertIn('"finish_reason": "error"', body)
        self.assertIn('"request_id": "rid-stream-missing-key"', body)

    def test_frontend_route_blocks_path_traversal(self):
        with patch.object(gateway_app_module, "FRONTEND_DIST_DIR", Path.cwd()):
            response = self.client.get("/..%2FREADME.md")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Forbidden"})

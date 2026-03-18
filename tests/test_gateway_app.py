import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.domain.execution import DuplicateRequestIdError
from backend.gateway import app as gateway_app_module
from backend.gateway.app import GatewayConfigurationError
from backend.gateway.admission import QueueFullError, QueueTimeoutError
from backend.gateway.app import app


class TestGatewayApp(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.state.shutdown_requested = False
        self._too_long_request_id = "r" * 257
        self._api_key_patcher = patch("backend.gateway.app._gateway_api_key", return_value="test-api-key")
        self._api_key_patcher.start()
        self.addCleanup(self._api_key_patcher.stop)

    @contextmanager
    def _frontend_dist_fixture(self):
        dist_dir = Path(__file__).resolve().parent / "fixtures" / "frontend_dist"
        with patch.object(gateway_app_module, "FRONTEND_DIST_DIR", dist_dir):
            yield "app.js"

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

    def test_chat_route_returns_409_for_duplicate_active_request_id(self):
        payload = {"message": "hello", "request_id": "rid-duplicate"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.slot.return_value.__aenter__ = AsyncMock(return_value=None)
            gate.slot.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("backend.gateway.app.asyncio.to_thread", side_effect=DuplicateRequestIdError("rid-duplicate")):
                response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "request_id already active"})

    def test_chat_route_returns_500_when_api_key_missing(self):
        payload = {"message": "hello", "request_id": "rid-misconfigured-chat"}
        self._api_key_patcher.stop()
        with patch(
            "backend.gateway.app._gateway_api_key",
            side_effect=GatewayConfigurationError("Server misconfigured: No API key found. Set NVIDIA_API_KEY in system env or .env."),
        ):
            response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"error": "Server misconfigured: No API key found. Set NVIDIA_API_KEY in system env or .env."},
        )

    def test_chat_route_rejects_too_long_request_id(self):
        response = self.client.post("/api/chat", json={"message": "hello", "request_id": self._too_long_request_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("request_id: too long", response.json()["error"])

    def test_chat_route_returns_503_while_shutdown_requested(self):
        app.state.shutdown_requested = True
        response = self.client.post("/api/chat", json={"message": "hello", "request_id": "rid-shutdown-chat"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Server shutting down"})

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
        self.assertEqual(response.headers["cache-control"], "no-cache, no-transform")
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
        self.assertEqual(response.headers["cache-control"], "no-cache, no-transform")
        body = response.text
        self.assertIn('"type": "error"', body)
        self.assertIn('"error": "gateway queue timeout"', body)
        self.assertIn('"type": "done"', body)
        self.assertIn('"finish_reason": "error"', body)
        self.assertIn('"request_id": "rid-stream-queue-timeout"', body)

    def test_chat_stream_success_uses_streaming_safe_cache_control(self):
        payload = {"message": "hello", "request_id": "rid-stream-success"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.acquire = AsyncMock(return_value=None)
            gate.release = AsyncMock(return_value=None)
            with patch(
                "backend.gateway.app.stream_chat",
                return_value=iter([{"type": "done", "finish_reason": "stop"}]),
            ):
                response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(response.headers["cache-control"], "no-cache, no-transform")
        self.assertIn('"finish_reason": "stop"', response.text)

    def test_chat_stream_duplicate_request_id_emits_error_and_done(self):
        payload = {"message": "hello", "request_id": "rid-stream-duplicate"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.acquire = AsyncMock(return_value=None)
            gate.release = AsyncMock(return_value=None)
            with patch(
                "backend.gateway.app.stream_chat",
                side_effect=DuplicateRequestIdError("rid-stream-duplicate"),
            ):
                response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('"type": "error"', body)
        self.assertIn('"error": "request_id already active"', body)
        self.assertIn('"type": "done"', body)
        self.assertIn('"finish_reason": "error"', body)

    def test_chat_stream_missing_api_key_emits_error_and_done(self):
        payload = {"message": "hello", "request_id": "rid-stream-misconfigured"}
        self._api_key_patcher.stop()
        with patch(
            "backend.gateway.app._gateway_api_key",
            side_effect=GatewayConfigurationError("Server misconfigured: No API key found. Set NVIDIA_API_KEY in system env or .env."),
        ):
            response = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('"type": "error"', body)
        self.assertIn('"error": "Server misconfigured: No API key found. Set NVIDIA_API_KEY in system env or .env."', body)
        self.assertIn('"type": "done"', body)
        self.assertIn('"finish_reason": "error"', body)

    def test_chat_stream_rejects_too_long_request_id(self):
        response = self.client.post("/api/chat/stream", json={"message": "hello", "request_id": self._too_long_request_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("request_id: too long", response.json()["error"])

    def test_chat_stream_returns_503_while_shutdown_requested(self):
        app.state.shutdown_requested = True
        response = self.client.post("/api/chat/stream", json={"message": "hello", "request_id": "rid-shutdown-stream"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Server shutting down"})

    def test_chat_route_runtime_error_still_maps_to_502(self):
        payload = {"message": "hello", "request_id": "rid-runtime-error"}
        with patch.object(gateway_app_module, "_ADMISSION_GATE") as gate:
            gate.slot.return_value.__aenter__ = AsyncMock(return_value=None)
            gate.slot.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("backend.gateway.app._gateway_api_key", return_value="test-key"):
                with patch("backend.gateway.app.chat_once", side_effect=RuntimeError("provider=openai | protocol=openai_responses | message=boom")):
                    response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Upstream request failed")
        self.assertIn("provider=openai", response.json()["detail"])

    def test_frontend_route_blocks_path_traversal(self):
        with patch.object(gateway_app_module, "FRONTEND_DIST_DIR", Path.cwd()):
            response = self.client.get("/..%2FREADME.md")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Forbidden"})

    def test_frontend_root_serves_index_with_no_cache(self):
        with self._frontend_dist_fixture():
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertIn("text/html", response.headers["content-type"])

    def test_frontend_spa_fallback_serves_index_with_no_cache(self):
        with self._frontend_dist_fixture():
            response = self.client.get("/chat")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertIn("text/html", response.headers["content-type"])

    def test_frontend_assets_are_served_with_immutable_cache_control(self):
        with self._frontend_dist_fixture() as asset_name:
            response = self.client.get(f"/assets/{asset_name}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")

    def test_cancel_route_stays_available_while_shutdown_requested(self):
        app.state.shutdown_requested = True
        with patch("backend.gateway.app.cancel_chat", return_value={"cancelled": True}) as cancel_mock:
            response = self.client.post("/api/chat/cancel", json={"request_id": "rid-shutdown-cancel"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cancelled": True})
        cancel_mock.assert_called_once_with("rid-shutdown-cancel")

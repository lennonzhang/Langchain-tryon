import signal
import sys
import types
import unittest
from unittest.mock import Mock, patch

from backend import server as server_module


class FakeUvicornServer:
    def __init__(self, config) -> None:
        self.config = config
        self.should_exit = False
        self.force_exit = False
        self.started = True
        self.handle_exit = None
        self._captured_signals = []
        self.run_called = False

    def run(self) -> None:
        self.run_called = True


class FakeUvicornServerNoCapturedSignals:
    """Simulates a uvicorn version without _captured_signals."""

    def __init__(self, config) -> None:
        self.config = config
        self.should_exit = False
        self.force_exit = False
        self.started = True
        self.handle_exit = None
        self.run_called = False

    def run(self) -> None:
        self.run_called = True


class ImmediateThread:
    def __init__(self, target=None, daemon=None, **kwargs) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        if self._target is not None:
            self._target()


class TestGracefulCancelServer(unittest.TestCase):
    def _build_server(self, callback):
        app = types.SimpleNamespace(state=types.SimpleNamespace(shutdown_requested=False))
        logger = Mock()
        fake_uvicorn = types.SimpleNamespace(Server=FakeUvicornServer)
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            server = server_module.GracefulCancelServer(
                config=object(),
                shutdown_cancel_drain_seconds=2.0,
                shutdown_callback=callback,
                app=app,
                logger=logger,
            )
        return server, app, logger

    def test_first_sigint_cancels_streams_then_exits(self):
        callback = Mock(
            return_value={
                "active_streams_before": 2,
                "cancelled_streams": 2,
                "drained": True,
                "active_streams_after": 0,
            }
        )
        server, app, logger = self._build_server(callback)

        with patch("backend.server.threading.Thread", ImmediateThread):
            server.handle_exit(signal.SIGINT, None)

        self.assertTrue(app.state.shutdown_requested)
        self.assertTrue(server._server.should_exit)
        self.assertFalse(server._server.force_exit)
        callback.assert_called_once_with()
        logger.info.assert_called()

    def test_first_sigint_exits_even_if_drain_times_out(self):
        callback = Mock(
            return_value={
                "active_streams_before": 1,
                "cancelled_streams": 1,
                "drained": False,
                "active_streams_after": 1,
            }
        )
        server, app, _logger = self._build_server(callback)

        with patch("backend.server.threading.Thread", ImmediateThread):
            server.handle_exit(signal.SIGINT, None)

        self.assertTrue(app.state.shutdown_requested)
        self.assertTrue(server._server.should_exit)
        self.assertFalse(server._server.force_exit)

    def test_second_sigint_forces_exit(self):
        callback = Mock(
            return_value={
                "active_streams_before": 1,
                "cancelled_streams": 1,
                "drained": False,
                "active_streams_after": 1,
            }
        )
        server, _app, _logger = self._build_server(callback)

        with patch("backend.server.threading.Thread", lambda *args, **kwargs: types.SimpleNamespace(start=lambda: None)):
            server.handle_exit(signal.SIGINT, None)

        self.assertFalse(server._server.should_exit)
        self.assertFalse(server._server.force_exit)

        server.handle_exit(signal.SIGINT, None)

        self.assertTrue(server._server.should_exit)
        self.assertTrue(server._server.force_exit)

    def test_non_sigint_exits_without_shutdown_drain(self):
        callback = Mock()
        server, app, _logger = self._build_server(callback)

        server.handle_exit(signal.SIGTERM, None)

        self.assertFalse(app.state.shutdown_requested)
        self.assertTrue(server._server.should_exit)
        self.assertFalse(server._server.force_exit)
        callback.assert_not_called()

    def test_handle_exit_tolerates_missing_captured_signals(self):
        callback = Mock(return_value={"active_streams_before": 0, "cancelled_streams": 0, "drained": True, "active_streams_after": 0})
        app = types.SimpleNamespace(state=types.SimpleNamespace(shutdown_requested=False))
        logger = Mock()
        fake_uvicorn = types.SimpleNamespace(Server=FakeUvicornServerNoCapturedSignals)
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            server = server_module.GracefulCancelServer(
                config=object(),
                shutdown_cancel_drain_seconds=2.0,
                shutdown_callback=callback,
                app=app,
                logger=logger,
            )

        with patch("backend.server.threading.Thread", ImmediateThread):
            server.handle_exit(signal.SIGINT, None)

        self.assertTrue(server._server.should_exit)

    def test_shutdown_callback_exception_still_sets_should_exit(self):
        callback = Mock(side_effect=RuntimeError("boom"))
        server, app, logger = self._build_server(callback)

        with patch("backend.server.threading.Thread", ImmediateThread):
            server.handle_exit(signal.SIGINT, None)

        self.assertTrue(app.state.shutdown_requested)
        self.assertTrue(server._server.should_exit)
        logger.exception.assert_called()

    def test_shutdown_callback_returns_none_still_sets_should_exit(self):
        callback = Mock(return_value=None)
        server, _app, _logger = self._build_server(callback)

        with patch("backend.server.threading.Thread", ImmediateThread):
            server.handle_exit(signal.SIGINT, None)

        self.assertTrue(server._server.should_exit)


class TestServerHelpers(unittest.TestCase):
    def test_shutdown_cancel_drain_seconds_defaults_to_two_seconds(self):
        with patch.dict("os.environ", {}, clear=False):
            self.assertEqual(server_module._shutdown_cancel_drain_seconds(), 2.0)

    def test_shutdown_cancel_drain_seconds_clamps_invalid_values(self):
        with patch.dict("os.environ", {"SHUTDOWN_CANCEL_DRAIN_SECONDS": "invalid"}, clear=False):
            self.assertEqual(server_module._shutdown_cancel_drain_seconds(), 2.0)
        with patch.dict("os.environ", {"SHUTDOWN_CANCEL_DRAIN_SECONDS": "-5"}, clear=False):
            self.assertEqual(server_module._shutdown_cancel_drain_seconds(), 0.0)

    def test_run_configures_logging_and_server(self):
        fake_app = types.SimpleNamespace(state=types.SimpleNamespace(shutdown_requested=True))
        config_mock = Mock(return_value="uvicorn-config")
        fake_uvicorn = types.SimpleNamespace(Config=config_mock)
        fake_gateway_app_module = types.SimpleNamespace(app=fake_app)
        fake_nvidia_client_module = types.SimpleNamespace(cancel_active_streams_for_shutdown=Mock(return_value={}))
        fake_env_loader_module = types.SimpleNamespace(load_env_file=Mock())
        fake_server_instance = Mock()

        with (
            patch.dict(
                sys.modules,
                {
                    "uvicorn": fake_uvicorn,
                    "backend.gateway.app": fake_gateway_app_module,
                    "backend.nvidia_client": fake_nvidia_client_module,
                    "backend.settings.env_loader": fake_env_loader_module,
                },
            ),
            patch("backend.chat_logger.configure_chat_logging") as configure_log_mock,
            patch("backend.chat_logger.attach_file_handler") as attach_handler_mock,
            patch("backend.server.GracefulCancelServer", return_value=fake_server_instance) as server_cls_mock,
            patch("logging.basicConfig") as basic_config_mock,
            patch.dict("os.environ", {"LOG_LEVEL": "WARNING"}, clear=False),
        ):
            server_module.run(chat_log_level="INFO")

        fake_env_loader_module.load_env_file.assert_called_once_with()
        configure_log_mock.assert_called_once_with("INFO")
        attach_handler_mock.assert_called_once_with()
        basic_config_mock.assert_called_once()
        self.assertEqual(basic_config_mock.call_args.kwargs["level"], 20)
        config_mock.assert_called_once_with(
            fake_app,
            host="127.0.0.1",
            port=8000,
            timeout_graceful_shutdown=3,
            log_config=None,
        )
        server_cls_mock.assert_called_once()
        fake_server_instance.run.assert_called_once_with()
        self.assertFalse(fake_app.state.shutdown_requested)

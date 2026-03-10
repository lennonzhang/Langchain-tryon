import os
import signal
import threading


def run(debug_stream: bool = False) -> None:
    import logging

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required. Install requirements.txt first.") from exc

    from .gateway.app import app
    from .nvidia_client import cancel_active_streams_for_shutdown

    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8000"))
    drain_timeout = _shutdown_cancel_drain_seconds()
    graceful_timeout = max(3, int(drain_timeout) + 1)
    if debug_stream:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app.state.debug_stream = bool(debug_stream)
    app.state.shutdown_requested = False
    mode = "on" if debug_stream else "off"
    print(f"Serving on http://{host}:{port} (debug-stream: {mode})")
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=graceful_timeout,
    )
    server = GracefulCancelServer(
        config=config,
        shutdown_cancel_drain_seconds=drain_timeout,
        shutdown_callback=lambda: cancel_active_streams_for_shutdown(drain_timeout),
        app=app,
        logger=logging.getLogger("uvicorn.error"),
    )
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.state.shutdown_requested = False


def _shutdown_cancel_drain_seconds() -> float:
    raw = os.getenv("SHUTDOWN_CANCEL_DRAIN_SECONDS", "").strip()
    if not raw:
        return 2.0
    try:
        value = float(raw)
    except ValueError:
        return 2.0
    return max(0.0, value)


class GracefulCancelServer:
    def __init__(self, *, config, shutdown_cancel_drain_seconds: float, shutdown_callback, app, logger) -> None:
        from uvicorn import Server

        self._server = Server(config=config)
        self._shutdown_cancel_drain_seconds = shutdown_cancel_drain_seconds
        self._shutdown_callback = shutdown_callback
        self._app = app
        self._logger = logger
        self._shutdown_started = False
        self._shutdown_lock = threading.Lock()

    def run(self) -> None:
        self._server.handle_exit = self.handle_exit
        self._server.run()

    def handle_exit(self, sig: int, frame) -> None:
        captured = getattr(self._server, "_captured_signals", None)
        if isinstance(captured, list):
            captured.append(sig)
        if self._server.should_exit and sig == signal.SIGINT:
            self._server.force_exit = True
            return
        if sig != signal.SIGINT:
            self._server.should_exit = True
            return
        with self._shutdown_lock:
            if self._shutdown_started:
                self._server.force_exit = True
                self._server.should_exit = True
                return
            self._shutdown_started = True
        threading.Thread(target=self._begin_graceful_shutdown, daemon=True).start()

    def _begin_graceful_shutdown(self) -> None:
        self._app.state.shutdown_requested = True
        self._logger.info(
            "SIGINT received, draining active streaming requests for up to %.2fs before shutdown",
            self._shutdown_cancel_drain_seconds,
        )
        try:
            result = self._shutdown_callback()
            if isinstance(result, dict):
                self._logger.info(
                    "Shutdown drain finished: active_before=%s cancelled=%s drained=%s active_after=%s",
                    result.get("active_streams_before", 0),
                    result.get("cancelled_streams", 0),
                    result.get("drained", False),
                    result.get("active_streams_after", 0),
                )
        except Exception:
            self._logger.exception("Shutdown callback failed")
        finally:
            self._server.should_exit = True


if __name__ == "__main__":
    run()

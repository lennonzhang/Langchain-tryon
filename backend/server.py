import os


def run(debug_stream: bool = False) -> None:
    import logging

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required. Install requirements.txt first.") from exc

    from .gateway.app import app

    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8000"))
    if debug_stream:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app.state.debug_stream = bool(debug_stream)
    mode = "on" if debug_stream else "off"
    print(f"Serving on http://{host}:{port} (debug-stream: {mode})")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()

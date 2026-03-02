import os
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .chat_handlers import handle_chat_once, handle_chat_stream
from .config import load_api_key
from .http_utils import send_json, serve_static
from .model_registry import capabilities_response

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"


class ChatHandler(BaseHTTPRequestHandler):
    api_key = load_api_key(BASE_DIR)
    debug_stream = False

    def do_GET(self) -> None:
        req_path = urlparse(self.path).path

        if req_path == "/api/capabilities":
            send_json(self, 200, capabilities_response())
            return

        if req_path.startswith("/api/"):
            send_json(self, 404, {"error": "Not found"})
            return

        if req_path == "/" or req_path.startswith("/assets/") or req_path == "/favicon.ico":
            serve_static(self, FRONTEND_DIST_DIR, "index.html" if req_path == "/" else req_path)
            return

        if "." not in req_path.rsplit("/", 1)[-1]:
            serve_static(self, FRONTEND_DIST_DIR, "index.html")
            return

        send_json(self, 404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path == "/api/chat":
            handle_chat_once(self, self.api_key, debug_stream=bool(self.debug_stream))
            return
        if self.path == "/api/chat/stream":
            handle_chat_stream(self, self.api_key, debug_stream=bool(self.debug_stream))
            return
        send_json(self, 404, {"error": "Not found"})


def run(debug_stream: bool = False) -> None:
    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8000"))
    if debug_stream:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ChatHandler.debug_stream = bool(debug_stream)
    server = ThreadingHTTPServer((host, port), ChatHandler)
    mode = "on" if debug_stream else "off"
    print(f"Serving on http://{host}:{port} (debug-stream: {mode})")
    server.serve_forever()


if __name__ == "__main__":
    run()

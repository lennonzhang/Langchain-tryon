import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .chat_handlers import handle_chat_once, handle_chat_stream
from .config import load_api_key
from .http_utils import send_json, serve_static

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


class ChatHandler(BaseHTTPRequestHandler):
    api_key = load_api_key(BASE_DIR)

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/static/"):
            serve_static(self, FRONTEND_DIR, "index.html" if self.path == "/" else self.path)
            return
        send_json(self, 404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path == "/api/chat":
            handle_chat_once(self, self.api_key)
            return
        if self.path == "/api/chat/stream":
            handle_chat_stream(self, self.api_key)
            return
        send_json(self, 404, {"error": "Not found"})


def run() -> None:
    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), ChatHandler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()

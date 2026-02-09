from http.server import BaseHTTPRequestHandler

from backend.chat_handlers import handle_chat_stream
from backend.config import load_api_key
from backend.http_utils import send_json


API_KEY = load_api_key()


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        handle_chat_stream(self, API_KEY)

    def do_GET(self) -> None:
        send_json(self, 405, {"error": "Method not allowed"})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        return

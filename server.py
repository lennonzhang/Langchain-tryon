import argparse

from backend.server import run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run local chat server.")
    parser.add_argument(
        "--chat-log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "debug", "info", "warning", "error"],
        help="Chat lifecycle log level (default: WARNING). Overrides CHAT_LOG_LEVEL env var.",
    )
    args = parser.parse_args()
    run(chat_log_level=args.chat_log_level)

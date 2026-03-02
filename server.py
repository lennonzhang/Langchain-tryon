import argparse

from backend.server import run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run local chat server.")
    parser.add_argument(
        "--debug-stream",
        action="store_true",
        help="Print streaming model feedback summary logs to console.",
    )
    args = parser.parse_args()
    run(debug_stream=bool(args.debug_stream))

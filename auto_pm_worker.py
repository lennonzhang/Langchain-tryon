import argparse

from backend.auto_pm.worker import AutoPmWorker


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Auto-PM sync worker.")
    parser.add_argument("--once", action="store_true", help="Run one sync pass and exit.")
    args = parser.parse_args()
    worker = AutoPmWorker()
    if args.once:
        worker.run_once()
    else:
        worker.run_forever()

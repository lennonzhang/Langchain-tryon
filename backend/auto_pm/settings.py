from __future__ import annotations

import os
from pathlib import Path

from backend.model_registry import get_default
from backend.settings.env_loader import env_int, load_env_file


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    load_env_file(_base_dir())
    root = os.getenv("AUTO_PM_DATA_DIR", "").strip()
    path = Path(root) if root else (_base_dir() / ".auto_pm")
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "autopm.sqlite3"


def owner_id() -> str:
    load_env_file(_base_dir())
    return os.getenv("AUTO_PM_OWNER_ID", "").strip() or "owner"


def owner_name() -> str:
    load_env_file(_base_dir())
    return os.getenv("AUTO_PM_OWNER_NAME", "").strip() or "Owner"


def dingtalk_project_root() -> Path | None:
    load_env_file(_base_dir())
    raw = os.getenv("AUTO_PM_DINGTALK_PROJECT_ROOT", "").strip()
    return Path(raw) if raw else None


def dingtalk_project_whitelist() -> set[str]:
    load_env_file(_base_dir())
    raw = os.getenv("AUTO_PM_DINGTALK_PROJECT_IDS", "").strip()
    return {item.strip() for item in raw.split(",") if item.strip()} if raw else set()


def worker_poll_seconds() -> int:
    return env_int("AUTO_PM_WORKER_POLL_SECONDS", 300, 5)


def auto_pm_model_id() -> str:
    load_env_file(_base_dir())
    return os.getenv("AUTO_PM_MODEL", "").strip() or str(get_default()["id"])

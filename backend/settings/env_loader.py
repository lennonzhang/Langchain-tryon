from __future__ import annotations

import os
from pathlib import Path

_LOADED_ENV_ROOTS: set[str] = set()


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_env_file(base_dir: Path | None = None) -> None:
    root = base_dir or Path(__file__).resolve().parents[2]
    root_key = str(root.resolve())
    if root_key in _LOADED_ENV_ROOTS:
        return
    candidates = [root / ".env", root.parent / ".env"]

    for file_path in candidates:
        if not file_path.exists() or not file_path.is_file():
            continue

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue

            os.environ.setdefault(key, _strip_quotes(value))
        _LOADED_ENV_ROOTS.add(root_key)
        return
    _LOADED_ENV_ROOTS.add(root_key)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def env_int(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def env_float(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value

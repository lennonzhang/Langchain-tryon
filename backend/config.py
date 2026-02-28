import os
from pathlib import Path


API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_env_file(base_dir: Path | None = None) -> None:
    root = base_dir or Path(__file__).resolve().parent.parent
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
        return


def load_api_key(base_dir: Path | None = None) -> str:
    root = base_dir or Path(__file__).resolve().parent.parent
    load_env_file(root)

    env_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if env_key:
        return env_key

    raise RuntimeError("No API key found. Set NVIDIA_API_KEY in system env or .env.")


def resolve_model(model: str | None) -> str:
    from .model_registry import get_by_id, get_default

    if isinstance(model, str) and get_by_id(model) is not None:
        return model
    return get_default()["id"]

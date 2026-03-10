from __future__ import annotations

import os
import threading

from .model_templates import MODEL_TEMPLATES

_PROVIDER_ENV_KEYS = {
    "nvidia": "NVIDIA_MODELS",
    "anthropic": "ANTHROPIC_MODELS",
    "openai": "OPENAI_MODELS",
    "google": "GOOGLE_MODELS",
}

_DEFAULT_AGENT_CONFIG: dict = {
    "max_steps": 6,
    "tools": ["web_search", "read_url", "request_user_input"],
    "enable_planning": False,
    "enable_reflection": False,
}

_ACTIVE: list[dict] = []
_ACTIVE_INDEX: dict[str, dict] = {}
_ACTIVE_LOCK = threading.Lock()


def _env_model_specs() -> list[tuple[str, str]] | None:
    specs: list[tuple[str, str]] = []
    any_set = False
    for provider, env_key in _PROVIDER_ENV_KEYS.items():
        raw = os.getenv(env_key, "").strip()
        if not raw:
            continue
        any_set = True
        for name in raw.split(","):
            name = name.strip()
            if name:
                specs.append((provider, name))
    return specs if any_set else None


def _template_for_provider(provider: str) -> dict | None:
    return next((model for model in MODEL_TEMPLATES if model["provider"] == provider), None)


def _resolve_active_models() -> list[dict]:
    specs = _env_model_specs()
    if specs is None:
        return [dict(model) for model in MODEL_TEMPLATES]

    result: list[dict] = []
    for provider, upstream in specs:
        existing = next(
            (
                model
                for model in MODEL_TEMPLATES
                if model["provider"] == provider and model["upstream_model"] == upstream
            ),
            None,
        )
        if existing:
            result.append(dict(existing))
            continue
        template = _template_for_provider(provider)
        if template is None:
            continue
        dynamic = dict(template)
        dynamic["id"] = f"{provider}/{upstream}"
        dynamic["label"] = upstream
        dynamic["default"] = False
        dynamic["upstream_model"] = upstream
        result.append(dynamic)

    if result and not any(model["default"] for model in result):
        result[0] = {**result[0], "default": True}
    return result


def _load_active() -> list[dict]:
    if not _ACTIVE:
        with _ACTIVE_LOCK:
            if not _ACTIVE:
                _ACTIVE.extend(_resolve_active_models())
                _ACTIVE_INDEX.update({model["id"]: model for model in _ACTIVE})
    return _ACTIVE


def reset_active() -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.clear()
        _ACTIVE_INDEX.clear()


class ModelCatalog:
    def get_all(self) -> list[dict]:
        return _load_active()

    def get_by_id(self, model_id: str | None) -> dict | None:
        _load_active()
        if not isinstance(model_id, str):
            return None
        return _ACTIVE_INDEX.get(model_id)

    def get_default(self) -> dict:
        active = _load_active()
        for model in active:
            if model["default"]:
                return model
        return active[0]

    def get_ids(self) -> tuple[str, ...]:
        return tuple(model["id"] for model in _load_active())

    def capabilities_response(self) -> dict:
        active = _load_active()
        return {
            "version": 1,
            "default": self.get_default()["id"],
            "models": [
                {
                    "id": model["id"],
                    "label": model["label"],
                    "capabilities": model["capabilities"],
                    "context_window": model["context_window"],
                }
                for model in active
            ],
        }

    def supports(self, model_id: str, capability: str) -> bool:
        model = self.get_by_id(model_id)
        if model is None:
            return False
        return bool(model["capabilities"].get(capability, False))

    def get_context_window(self, model_id: str) -> int:
        model = self.get_by_id(model_id)
        return model["context_window"] if model else 128_000

    def get_params(self, model_id: str) -> dict:
        model = self.get_by_id(model_id)
        return dict(model["params"]) if model else {}

    def get_provider(self, model_id: str) -> str:
        model = self.get_by_id(model_id)
        if model is None:
            return "nvidia"
        return str(model.get("provider", "nvidia"))

    def get_upstream_model(self, model_id: str) -> str:
        model = self.get_by_id(model_id)
        if model is None:
            return model_id
        return str(model.get("upstream_model", model_id))

    def get_protocol(self, model_id: str) -> str:
        model = self.get_by_id(model_id)
        if model is None:
            return "nvidia_chat_completions"
        return str(model.get("protocol", "nvidia_chat_completions"))

    def get_agent_config(self, model_id: str) -> dict:
        model = self.get_by_id(model_id)
        if model is None:
            return dict(_DEFAULT_AGENT_CONFIG)
        return dict(model.get("agent_config", _DEFAULT_AGENT_CONFIG))


catalog = ModelCatalog()

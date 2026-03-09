"""Compatibility facade over the env-driven model catalog."""

from __future__ import annotations

from backend.domain.model_catalog import catalog, reset_active
from backend.domain.model_templates import MODEL_TEMPLATES

_REGISTRY = MODEL_TEMPLATES
_INDEX: dict[str, dict] = {model["id"]: model for model in MODEL_TEMPLATES}


def _reset_active() -> None:
    reset_active()


def get_all() -> list[dict]:
    return catalog.get_all()


def get_by_id(model_id: str) -> dict | None:
    return catalog.get_by_id(model_id)


def get_default() -> dict:
    return catalog.get_default()


def get_ids() -> tuple[str, ...]:
    return catalog.get_ids()


def supports(model_id: str, capability: str) -> bool:
    return catalog.supports(model_id, capability)


def get_context_window(model_id: str) -> int:
    return catalog.get_context_window(model_id)


def get_params(model_id: str) -> dict:
    return catalog.get_params(model_id)


def get_provider(model_id: str) -> str:
    return catalog.get_provider(model_id)


def get_upstream_model(model_id: str) -> str:
    return catalog.get_upstream_model(model_id)


def get_protocol(model_id: str) -> str:
    return catalog.get_protocol(model_id)


def get_agent_config(model_id: str) -> dict:
    return catalog.get_agent_config(model_id)


def capabilities_response() -> dict:
    return catalog.capabilities_response()

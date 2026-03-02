"""Centralised model capability registry — the single source of truth.

Every model-specific behaviour (thinking, media, agent routing, temperature,
context window …) is declared here.  Both backend modules and the
``/api/capabilities`` endpoint consume this registry so that the frontend
never needs to hard-code ``startsWith()`` rules.
"""

from __future__ import annotations

_REGISTRY: list[dict] = [
    {
        "id": "moonshotai/kimi-k2.5",
        "label": "Kimi K2.5",
        "default": True,
        "capabilities": {
            "thinking": True,
            "media": True,
            "agent": False,
        },
        "params": {
            "temperature_thinking": 1.0,
            "temperature_standard": 0.6,
            "top_p": 1.0,
            "thinking_control": "call_time",
            "thinking_kwarg_key": "chat_template_kwargs",
            "thinking_kwarg_field": "thinking",
        },
        "context_window": 131072,
    },
    {
        "id": "qwen/qwen3.5-397b-a17b",
        "label": "Qwen 3.5",
        "default": False,
        "capabilities": {
            "thinking": True,
            "media": False,
            "agent": True,
        },
        "params": {
            "temperature_thinking": 0.6,
            "temperature_standard": 0.6,
            "top_p": 0.95,
            "thinking_control": "call_time",
            "thinking_kwarg_key": "chat_template_kwargs",
            "thinking_kwarg_field": "enable_thinking",
        },
        "context_window": 128000,
        "agent_config": {
            "max_steps": 8,
            "tools": ["web_search", "read_url", "python_exec"],
            "enable_planning": True,
            "enable_reflection": True,
        },
    },
    {
        "id": "z-ai/glm5",
        "label": "GLM 5",
        "default": False,
        "capabilities": {
            "thinking": True,
            "media": False,
            "agent": True,
        },
        "params": {
            "temperature_thinking": 0.7,
            "temperature_standard": 0.7,
            "top_p": 1.0,
            "thinking_control": "construct_time",
            "thinking_kwarg_key": "extra_body",
            "thinking_kwarg_field": "chat_template_kwargs",
        },
        "context_window": 128000,
        "agent_config": {
            "max_steps": 8,
            "tools": ["web_search", "read_url", "python_exec"],
            "enable_planning": True,
            "enable_reflection": True,
        },
    },
]

# ── public helpers ───────────────────────────────────────────────

def get_all() -> list[dict]:
    """Return the full registry list (read-only intent)."""
    return _REGISTRY


def get_by_id(model_id: str) -> dict | None:
    """Look up a model descriptor by its exact ``id`` string."""
    for m in _REGISTRY:
        if m["id"] == model_id:
            return m
    return None


def get_default() -> dict:
    """Return the descriptor marked ``"default": True``."""
    for m in _REGISTRY:
        if m["default"]:
            return m
    return _REGISTRY[0]


def get_ids() -> tuple[str, ...]:
    """Return all registered model id strings as a tuple."""
    return tuple(m["id"] for m in _REGISTRY)


def supports(model_id: str, capability: str) -> bool:
    """Check whether *model_id* declares *capability* (thinking/media/agent)."""
    m = get_by_id(model_id)
    if m is None:
        return False
    return bool(m["capabilities"].get(capability, False))


def get_context_window(model_id: str) -> int:
    """Return the context window size for *model_id*, default 128 000."""
    m = get_by_id(model_id)
    return m["context_window"] if m else 128_000


def get_params(model_id: str) -> dict:
    """Return the model-specific parameter dict, or empty dict if unknown."""
    m = get_by_id(model_id)
    return dict(m["params"]) if m else {}


_DEFAULT_AGENT_CONFIG: dict = {
    "max_steps": 6,
    "tools": ["web_search", "read_url"],
    "enable_planning": False,
    "enable_reflection": False,
}


def get_agent_config(model_id: str) -> dict:
    """Return the agent configuration for *model_id*.

    Falls back to ``_DEFAULT_AGENT_CONFIG`` when the model has no
    ``agent_config`` entry or is unknown.
    """
    m = get_by_id(model_id)
    if m is None:
        return dict(_DEFAULT_AGENT_CONFIG)
    return dict(m.get("agent_config", _DEFAULT_AGENT_CONFIG))


def capabilities_response() -> dict:
    """Build the JSON shape served at ``GET /api/capabilities``."""
    return {
        "version": 1,
        "default": get_default()["id"],
        "models": [
            {
                "id": m["id"],
                "label": m["label"],
                "capabilities": m["capabilities"],
                "context_window": m["context_window"],
            }
            for m in _REGISTRY
        ],
    }

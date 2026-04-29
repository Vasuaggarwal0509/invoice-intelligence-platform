"""Typed configuration.

Two layers:
* :class:`Settings` — env-var-driven (secrets, toggles, paths).
* :class:`RuntimeConfig` — JSON-file-driven (operator-editable lists).
"""

from .runtime_config import RuntimeConfig, get_runtime_config
from .settings import Settings, get_settings

__all__ = ["RuntimeConfig", "Settings", "get_runtime_config", "get_settings"]

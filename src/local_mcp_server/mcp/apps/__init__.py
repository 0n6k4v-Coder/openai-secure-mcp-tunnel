from __future__ import annotations

from .registration import register_all_apps
from .terminal import TERMINAL_APP_URI, register_terminal_app

__all__ = [
    "TERMINAL_APP_URI",
    "register_all_apps",
    "register_terminal_app",
]

"""OS-aware default paths for temp, config, and audit-log roots.

These are deliberately not CLI-overridable. The config file (loaded by
``config.py``) may override ``temp_root``; nothing else is mutable at runtime.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _windows_localappdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def _windows_appdata() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Roaming"


def _xdg(env_var: str, default_under_home: str) -> Path:
    base = os.environ.get(env_var)
    if base:
        return Path(base)
    return Path.home() / default_under_home


def default_temp_root() -> Path:
    if sys.platform == "win32":
        return _windows_localappdata() / "sf-clean-room" / "temp"
    return _xdg("XDG_CACHE_HOME", ".cache") / "sf-clean-room" / "temp"


def default_config_path() -> Path:
    if sys.platform == "win32":
        return _windows_appdata() / "sf-clean-room" / "config.toml"
    return _xdg("XDG_CONFIG_HOME", ".config") / "sf-clean-room" / "config.toml"


def default_log_dir() -> Path:
    if sys.platform == "win32":
        return _windows_localappdata() / "sf-clean-room" / "logs"
    return _xdg("XDG_STATE_HOME", ".local/state") / "sf-clean-room" / "logs"

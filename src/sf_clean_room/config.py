"""Read the fixed-location config file.

v1 supports exactly one key: ``temp_root``. Missing file or missing key yields
the OS-aware default from ``paths.default_temp_root``.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from sf_clean_room.paths import default_config_path, default_temp_root


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    temp_root: Path
    source_path: Path | None  # the config file actually read, or None for pure defaults


def load_config(config_path: Path | None = None) -> Config:
    path = config_path if config_path is not None else default_config_path()
    if not path.exists():
        return Config(temp_root=default_temp_root().resolve(), source_path=None)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Config file is not valid TOML: {path}: {e}") from e
    raw_temp = data.get("temp_root")
    if raw_temp is None:
        temp_root = default_temp_root()
    elif isinstance(raw_temp, str) and raw_temp:
        temp_root = Path(raw_temp).expanduser()
    else:
        raise ConfigError(f"temp_root in {path} must be a non-empty string")
    return Config(temp_root=temp_root.resolve(), source_path=path)

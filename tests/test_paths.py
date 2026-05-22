import os
import sys

import pytest

from sf_clean_room import paths


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX defaults")
def test_xdg_cache_home_overrides_temp_root(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert paths.default_temp_root() == tmp_path / "sf-clean-room" / "temp"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX defaults")
def test_xdg_config_home_overrides_config_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert paths.default_config_path() == tmp_path / "sf-clean-room" / "config.toml"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX defaults")
def test_xdg_state_home_overrides_log_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert paths.default_log_dir() == tmp_path / "sf-clean-room" / "logs"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows defaults")
def test_localappdata_overrides_temp_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.default_temp_root() == tmp_path / "sf-clean-room" / "temp"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows defaults")
def test_appdata_overrides_config_path(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.default_config_path() == tmp_path / "sf-clean-room" / "config.toml"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows defaults")
def test_localappdata_overrides_log_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.default_log_dir() == tmp_path / "sf-clean-room" / "logs"

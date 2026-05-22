import pytest

from sf_clean_room.config import ConfigError, load_config


def test_missing_config_returns_default_temp_root(tmp_path):
    cfg = load_config(config_path=tmp_path / "does-not-exist.toml")
    assert cfg.source_path is None
    assert cfg.temp_root.is_absolute()


def test_explicit_temp_root_is_honoured(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('temp_root = "%s"\n' % (tmp_path / "elsewhere").as_posix(), encoding="utf-8")
    cfg = load_config(config_path=cfg_file)
    assert cfg.temp_root == (tmp_path / "elsewhere").resolve()
    assert cfg.source_path == cfg_file


def test_empty_temp_root_rejected(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('temp_root = ""\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path=cfg_file)


def test_invalid_toml_rejected(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("this is = not = valid toml\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path=cfg_file)


def test_missing_temp_root_key_uses_default(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("# empty config\n", encoding="utf-8")
    cfg = load_config(config_path=cfg_file)
    assert cfg.source_path == cfg_file
    assert cfg.temp_root.is_absolute()

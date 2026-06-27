"""Offline tests for code_analysis_pipeline (get_code_analysis).

All sf CLI calls are mocked so no network, Salesforce session, or installed
sf code-analyzer plugin is needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.code_analysis_pipeline import (
    SENTINEL_NAME,
    _check_java,
    _check_metadata,
    _check_plugin,
    _stem,
    dry_run,
    execute,
)
from sf_clean_room.sfcli import SfCliError

_ALIAS = "test_org"


# ---------------------------------------------------------------------------
# _stem
# ---------------------------------------------------------------------------

def test_stem():
    assert _stem("myorg") == "code_analyser_results_myorg"


# ---------------------------------------------------------------------------
# _check_metadata
# ---------------------------------------------------------------------------

def test_check_metadata_missing_dir(tmp_path):
    with pytest.raises((ValueError, RuntimeError)):
        _check_metadata(tmp_path / "nonexistent")


def test_check_metadata_no_package_xml(tmp_path):
    d = tmp_path / "meta"
    d.mkdir()
    with pytest.raises((ValueError, RuntimeError), match="package.xml"):
        _check_metadata(d)


def test_check_metadata_ok(tmp_path):
    d = tmp_path / "meta"
    d.mkdir()
    (d / "package.xml").write_text("<Package/>", encoding="utf-8")
    _check_metadata(d)  # must not raise


# ---------------------------------------------------------------------------
# _check_plugin
# ---------------------------------------------------------------------------

def test_check_plugin_missing(tmp_path):
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=SfCliError("not found")):
        with pytest.raises(RuntimeError, match="code-analyzer"):
            with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
                _check_plugin(log)


def test_check_plugin_present(tmp_path):
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", return_value="help text"):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            _check_plugin(log)  # must not raise


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

def _metadata_dir(tmp_path: Path) -> Path:
    d = tmp_path / "meta"
    d.mkdir()
    (d / "package.xml").write_text("<Package/>", encoding="utf-8")
    return d


def test_dry_run_lists_output_files(tmp_path):
    meta = _metadata_dir(tmp_path)
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", return_value=""):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            report = dry_run(_ALIAS, meta, log)
    assert f"code_analyser_results_{_ALIAS}.html" in report
    assert f"code_analyser_results_{_ALIAS}.csv" in report
    assert f"code_analyser_results_{_ALIAS}.json" in report
    assert SENTINEL_NAME in report


def test_dry_run_fails_missing_plugin(tmp_path):
    meta = _metadata_dir(tmp_path)
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=SfCliError("no plugin")):
        with pytest.raises(RuntimeError, match="code-analyzer"):
            with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
                dry_run(_ALIAS, meta, log)


def test_dry_run_fails_missing_package_xml(tmp_path):
    meta = tmp_path / "meta"
    meta.mkdir()
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", return_value=""):
        with pytest.raises((ValueError, RuntimeError), match="package.xml"):
            with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
                dry_run(_ALIAS, meta, log)


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def _make_analyzer_output(run_temp: Path, alias: str) -> None:
    """Simulate sf code-analyzer writing its three output files."""
    stem = f"code_analyser_results_{alias}"
    (run_temp / f"{stem}.html").write_text("<html/>", encoding="utf-8")
    (run_temp / f"{stem}.csv").write_text("rule,engine\n", encoding="utf-8")
    (run_temp / f"{stem}.json").write_text(
        json.dumps({
            "violationCounts": {"total": 42, "sev2": 10, "sev3": 20, "sev4": 8, "sev5": 4},
            "versions": {"pmd": "7.0.0", "eslint": "8.0.0"},
            "violations": [],
        }),
        encoding="utf-8",
    )


def _make_run_cli_text_stub(alias: str):
    """Return a run_cli_text stub that writes fake analyzer output to the temp dir."""
    def _stub(cmd, timeout=None):
        # The temp dir is the parent of the .html output file (cmd contains it).
        for i, arg in enumerate(cmd):
            if arg == "--output-file" and cmd[i + 1].endswith(".html"):
                run_temp = Path(cmd[i + 1]).parent
                _make_analyzer_output(run_temp, alias)
                return ""
        return ""
    return _stub


def test_execute_writes_sentinel(tmp_path):
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    stub = _make_run_cli_text_stub(_ALIAS)
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=stub):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)

    assert (publish_path / SENTINEL_NAME).exists(), "sentinel must be present"


def test_execute_sentinel_is_valid_json(tmp_path):
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    stub = _make_run_cli_text_stub(_ALIAS)
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=stub):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)

    data = json.loads((publish_path / SENTINEL_NAME).read_text(encoding="utf-8"))
    assert data["org_alias"] == _ALIAS
    assert "violation_counts" in data
    assert data["violation_counts"]["total"] == 42
    assert "engine_versions" in data
    assert "output_files" in data


def test_execute_three_report_files_published(tmp_path):
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    stub = _make_run_cli_text_stub(_ALIAS)
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=stub):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)

    stem = _stem(_ALIAS)
    assert (publish_path / f"{stem}.html").exists()
    assert (publish_path / f"{stem}.csv").exists()
    assert (publish_path / f"{stem}.json").exists()


def test_execute_sentinel_is_last_by_mtime(tmp_path):
    """_summary.json must be the last file moved (highest or equal mtime)."""
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    stub = _make_run_cli_text_stub(_ALIAS)
    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=stub):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)

    sentinel_mtime = (publish_path / SENTINEL_NAME).stat().st_mtime
    for p in publish_path.iterdir():
        if p.name != SENTINEL_NAME:
            assert p.stat().st_mtime <= sentinel_mtime + 0.01


def test_execute_analyzer_failure_does_not_publish(tmp_path):
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    (publish_path / "old_file.txt").write_text("prior", encoding="utf-8")

    with patch(
        "sf_clean_room.code_analysis_pipeline.run_cli_text",
        side_effect=SfCliError("analyzer crashed"),
    ):
        with pytest.raises(RuntimeError, match="code-analyzer"):
            with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
                execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)

    # Sentinel must NOT exist; publish path must be untouched
    assert not (publish_path / SENTINEL_NAME).exists()
    assert (publish_path / "old_file.txt").read_text(encoding="utf-8") == "prior"


def test_execute_passes_workspace_and_target_to_cli(tmp_path):
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    captured_cmds = []

    def _stub(cmd, timeout=None):
        captured_cmds.append(list(cmd))
        for i, arg in enumerate(cmd):
            if arg == "--output-file" and cmd[i + 1].endswith(".html"):
                run_temp = Path(cmd[i + 1]).parent
                _make_analyzer_output(run_temp, _ALIAS)
                return ""
        return ""

    with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=_stub):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)

    run_cmd = [c for c in captured_cmds if "run" in c and "--target" in c]
    assert run_cmd, "sf code-analyzer run command not captured"
    cmd = run_cmd[0]
    target_idx = cmd.index("--target") + 1
    assert Path(cmd[target_idx]) == meta.resolve()
    # --workspace must be present and equal to the metadata path so the command
    # is cwd-independent (without it, sf code-analyzer defaults workspace to cwd
    # and rejects targets that don't sit underneath it).
    assert "--workspace" in cmd, "--workspace flag must be passed"
    ws_idx = cmd.index("--workspace") + 1
    assert Path(cmd[ws_idx]) == meta.resolve()


# ---------------------------------------------------------------------------
# _check_java
# ---------------------------------------------------------------------------

def test_check_java_present(tmp_path):
    with patch("sf_clean_room.code_analysis_pipeline.shutil.which", return_value="/usr/bin/java"):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            result = _check_java(log)
    assert result is True


def test_check_java_missing_returns_false_and_warns(tmp_path):
    with patch("sf_clean_room.code_analysis_pipeline.shutil.which", return_value=None):
        with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
            result = _check_java(log)
    assert result is False
    log_text = (tmp_path / "logs").glob("*.log")
    content = next(log_text).read_text(encoding="utf-8")
    assert "java" in content.lower()
    assert "PMD" in content or "pmd" in content.lower()


def test_execute_proceeds_when_java_missing(tmp_path):
    """Java absence should warn but not abort — sf code-analyzer itself handles engine failures."""
    meta = _metadata_dir(tmp_path)
    publish_path = tmp_path / "out"
    publish_path.mkdir()
    stub = _make_run_cli_text_stub(_ALIAS)
    with patch("sf_clean_room.code_analysis_pipeline.shutil.which", return_value=None):
        with patch("sf_clean_room.code_analysis_pipeline.run_cli_text", side_effect=stub):
            with audit_log(_ALIAS, log_dir=tmp_path / "logs") as log:
                execute(_ALIAS, meta, publish_path, tmp_path / "temp", log)
    assert (publish_path / SENTINEL_NAME).exists()

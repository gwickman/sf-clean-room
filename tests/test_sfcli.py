"""Tests for sfcli.py — focusing on cross-platform argv[0] resolution.

On Windows, bare "sf"/"sfdx" in cmd[0] would cause [WinError 2] because npm
installs the CLI as sf.CMD (no .exe).  run_cli_text() must call which_cli()
to get the full path before spawning the process.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sf_clean_room.sfcli import SfCliError, run_cli_text, which_cli


# ---------------------------------------------------------------------------
# which_cli
# ---------------------------------------------------------------------------

def test_which_cli_finds_sf():
    with patch("sf_clean_room.sfcli.shutil.which", side_effect=lambda n: r"C:\fake\sf.CMD" if n == "sf" else None):
        path, flavor = which_cli()
    assert path == r"C:\fake\sf.CMD"
    assert flavor == "sf"


def test_which_cli_falls_back_to_sfdx():
    with patch("sf_clean_room.sfcli.shutil.which", side_effect=lambda n: r"C:\fake\sfdx.CMD" if n == "sfdx" else None):
        path, flavor = which_cli()
    assert path == r"C:\fake\sfdx.CMD"
    assert flavor == "sfdx"


def test_which_cli_raises_when_neither_found():
    with patch("sf_clean_room.sfcli.shutil.which", return_value=None):
        with pytest.raises(SfCliError, match="not found on PATH"):
            which_cli()


# ---------------------------------------------------------------------------
# run_cli_text — argv[0] resolution
# ---------------------------------------------------------------------------

def _make_proc(returncode=0, stdout="", stderr=""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def test_run_cli_text_resolves_bare_sf():
    """Bare 'sf' in cmd[0] must be replaced with the full CLI path."""
    captured = []

    def _fake_run(cmd, **kw):
        captured.append(list(cmd))
        return _make_proc()

    with patch("sf_clean_room.sfcli.which_cli", return_value=(r"C:\npm\sf.CMD", "sf")):
        with patch("subprocess.run", side_effect=_fake_run):
            run_cli_text(["sf", "code-analyzer", "run", "--help"])

    assert captured[0][0] == r"C:\npm\sf.CMD"
    assert captured[0][1:] == ["code-analyzer", "run", "--help"]


def test_run_cli_text_resolves_bare_sfdx():
    """Bare 'sfdx' in cmd[0] is resolved the same way."""
    captured = []

    with patch("sf_clean_room.sfcli.which_cli", return_value=(r"C:\npm\sfdx.CMD", "sfdx")):
        with patch("subprocess.run", side_effect=lambda cmd, **kw: (captured.append(list(cmd)), _make_proc())[1]):
            run_cli_text(["sfdx", "org:list"])

    assert captured[0][0] == r"C:\npm\sfdx.CMD"


def test_run_cli_text_full_path_not_re_resolved():
    """A full path in cmd[0] is passed through unchanged — which_cli() not called."""
    captured = []
    full_path = r"C:\already\resolved\sf.CMD"

    with patch("sf_clean_room.sfcli.which_cli", side_effect=AssertionError("should not call which_cli")):
        with patch("subprocess.run", side_effect=lambda cmd, **kw: (captured.append(list(cmd)), _make_proc())[1]):
            run_cli_text([full_path, "--version"])

    assert captured[0][0] == full_path


def test_run_cli_text_cli_not_found_raises_sfclierror():
    """If CLI is not on PATH, run_cli_text raises SfCliError (not FileNotFoundError)."""
    with patch("sf_clean_room.sfcli.which_cli", side_effect=SfCliError("Salesforce CLI not found on PATH")):
        with pytest.raises(SfCliError, match="not found on PATH"):
            run_cli_text(["sf", "--version"])


def test_run_cli_text_nonzero_exit_raises_sfclierror():
    with patch("sf_clean_room.sfcli.which_cli", return_value=(r"/usr/bin/sf", "sf")):
        with patch("subprocess.run", return_value=_make_proc(returncode=1, stderr="boom")):
            with pytest.raises(SfCliError, match="boom"):
                run_cli_text(["sf", "--version"])

import pytest

from sf_clean_room import __version__
from sf_clean_room.cli import build_parser, main


def test_top_level_help_lists_commands(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "get_metadata" in out
    assert "Authentication" in out
    assert "Exit codes" in out


def test_version_flag(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_get_metadata_help_runs_without_auth(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["get_metadata", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    # Per-command help must contain the contract details for grounding an agent.
    assert "--org-alias" in out
    assert "--path" in out
    assert "--dry-run" in out
    assert "package.xml" in out
    assert "Deny list" in out


def test_get_metadata_help_documents_skip_log(capsys):
    # v2.1: per-command help documents the limited-permission skip log, generated
    # from the SKIP_BUCKETS constant so it cannot drift from runtime.
    from sf_clean_room.constants import SKIP_BUCKETS
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["get_metadata", "--help"])
    out = capsys.readouterr().out
    assert "_skipped-types.csv" in out
    for bucket in SKIP_BUCKETS:
        assert bucket in out


def test_no_command_prints_help_and_returns_nonzero(capsys):
    rc = main([])
    assert rc != 0


def test_get_metadata_requires_org_alias(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["get_metadata", "--path", "./out"])
    assert exc.value.code != 0


def test_get_metadata_requires_path(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["get_metadata", "--org-alias", "myorg"])
    assert exc.value.code != 0


def test_unknown_command_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["not_a_command"])
    assert exc.value.code != 0

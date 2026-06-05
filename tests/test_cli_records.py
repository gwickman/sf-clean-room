import pytest

from sf_clean_room.cli import build_parser


def test_top_level_help_lists_get_records(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "get_records" in out


def test_get_records_help_runs_without_auth(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["get_records", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for token in ("--org-alias", "--path", "--only", "--where", "--plan", "--dry-run"):
        assert token in out
    # Grounding content for an agent.
    assert "_field-handling-applied.csv" in out
    assert "special-category" in out.lower()
    assert "read-only" in out.lower()


def test_get_records_parses_flags():
    args = build_parser().parse_args([
        "get_records", "--org-alias", "myorg", "--path", "./out",
        "--only", "Account", "Contact", "--plan", "p.toml", "--dry-run",
    ])
    assert args.org_alias == "myorg"
    assert args.only == ["Account", "Contact"]
    assert args.plan == "p.toml"
    assert args.dry_run is True


def test_get_records_requires_org_alias():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["get_records", "--path", "./out"])


def test_get_records_requires_path():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["get_records", "--org-alias", "myorg"])

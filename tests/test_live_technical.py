"""Live integration tests for get_technical_objects.

Marked ``live`` — skipped automatically unless the test org is authenticated
(see ``tests/live_org.toml`` and ``tests/conftest.py``).  Run with:

    pytest -m live tests/test_live_technical.py -s

These tests exercise the real org defined in ``live_org.toml``.  Some objects
will be absent or permission-gated in a Developer Edition org — those are
recorded as expected skips in regression-testing.md.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from sf_clean_room.audit import audit_log
from sf_clean_room.config import load_config
from sf_clean_room.session import get_session
from sf_clean_room.technical_pipeline import (
    SENTINEL_NAME,
    SUMMARY_NAME,
    TechnicalRequest,
    dry_run,
    execute,
)
from sf_clean_room.constants import API_VERSION

# Matches only raw (unmasked) IPs — last octet non-zero. Derived network prefixes
# end in .0 and are the expected DERIVE/ip_prefix output, so they must NOT match.
_DOTTED_QUAD = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.[1-9]\d*\b")
_EMAIL_IN_CLEAR = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


@pytest.fixture(scope="module")
def session(live_org):
    return get_session(live_org, api_version=API_VERSION)


@pytest.fixture(scope="module")
def output_base(tmp_path_factory):
    import tomllib
    toml_path = Path(__file__).parent / "live_org.toml"
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    base = Path(cfg.get("output_dir", ".test-output")) / "technical_objects"
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.mark.live
def test_dry_run_produces_column_plan(live_org, session, output_base, tmp_path):
    plan_path = tmp_path / "plan.toml"
    req = TechnicalRequest(only=None, limit=None, plan_path=plan_path, dry_run=True)
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        report = dry_run(session, output_base, req, log)

    assert "dry-run" in report
    assert plan_path.exists()
    plan_content = plan_path.read_text(encoding="utf-8")
    assert "[scope]" in plan_content
    assert "[overrides]" in plan_content
    # At least some objects should appear in the plan.
    assert "ApexClass" in plan_content or "Organization" in plan_content


@pytest.mark.live
def test_dry_run_exits_without_publish(live_org, session, tmp_path):
    # Use an isolated tmp_path so a sentinel from a prior real-run cannot
    # pre-exist and cause a false failure.
    out = tmp_path / "out"
    req = TechnicalRequest(only=["Organization"], limit=None, plan_path=None, dry_run=True)
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        dry_run(session, out, req, log)
    # Sentinel must NOT be present; dry-run must not write to the publish path.
    assert not (out / SENTINEL_NAME).exists()
    assert not out.exists() or not any(out.iterdir())


@pytest.mark.live
def test_real_run_limited_publishes_sentinel(live_org, session, output_base, tmp_path):
    config = load_config()
    req = TechnicalRequest(
        only=["ApexClass", "Organization", "limits", "recordCount"],
        limit=50,
        plan_path=None,
        dry_run=False,
    )
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        publish_path = execute(session, output_base, req, config.temp_root, log)

    assert (publish_path / SENTINEL_NAME).exists(), "sentinel must be present"
    assert (publish_path / SUMMARY_NAME).exists(), "summary must be present"


@pytest.mark.live
def test_real_run_no_raw_ips_in_csvs(live_org, session, output_base, tmp_path):
    """After a limited run, verify no dotted-quad IPs appear verbatim in any CSV."""
    config = load_config()
    req = TechnicalRequest(
        only=["LoginHistory", "AuthSession"],
        limit=50,
        plan_path=None,
        dry_run=False,
    )
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        publish_path = execute(session, output_base, req, config.temp_root, log)

    for csv_path in publish_path.glob("*.csv"):
        if csv_path.name == SENTINEL_NAME:
            continue
        content = csv_path.read_text(encoding="utf-8")
        for line in content.splitlines()[1:]:  # skip header
            m = _DOTTED_QUAD.search(line)
            if m:
                pytest.fail(
                    f"Dotted-quad IP found verbatim in {csv_path.name}: {m.group()!r}\n"
                    f"  Line: {line[:200]}"
                )


@pytest.mark.live
def test_real_run_no_clear_emails_in_csvs(live_org, session, output_base, tmp_path):
    """Verify no email-like strings appear verbatim in published CSV data rows."""
    config = load_config()
    req = TechnicalRequest(
        only=["Group", "Organization"],
        limit=50,
        plan_path=None,
        dry_run=False,
    )
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        publish_path = execute(session, output_base, req, config.temp_root, log)

    for csv_path in publish_path.glob("*.csv"):
        if csv_path.name in (SENTINEL_NAME, SUMMARY_NAME):
            continue
        with open(csv_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col, val in row.items():
                    if _EMAIL_IN_CLEAR.search(val or ""):
                        # Only fail if the column is not a HASH column
                        # (sentinel records the action; accept hashed hex strings).
                        if not re.fullmatch(r"[0-9a-f]{64}", val):
                            pytest.fail(
                                f"Email-like value in {csv_path.name}[{col}]: {val!r}"
                            )


@pytest.mark.live
def test_real_run_sentinel_is_last(live_org, session, output_base, tmp_path):
    """Sentinel mtime must not be older than any other file in the publish folder."""
    config = load_config()
    req = TechnicalRequest(
        only=["limits"],
        limit=None,
        plan_path=None,
        dry_run=False,
    )
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        publish_path = execute(session, output_base, req, config.temp_root, log)

    sentinel_mtime = (publish_path / SENTINEL_NAME).stat().st_mtime
    for f in publish_path.iterdir():
        if f.name != SENTINEL_NAME:
            assert sentinel_mtime >= f.stat().st_mtime - 0.01


@pytest.mark.live
def test_rerun_snapshot_replaces_cleanly(live_org, session, output_base, tmp_path):
    """A second run should clear and republish without error."""
    config = load_config()
    req = TechnicalRequest(
        only=["limits"],
        limit=None,
        plan_path=None,
        dry_run=False,
    )
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        execute(session, output_base, req, config.temp_root, log)
    with audit_log(live_org, log_dir=tmp_path / "logs2") as log2:
        execute(session, output_base, req, config.temp_root, log2)
    assert (output_base / SENTINEL_NAME).exists()


@pytest.mark.live
def test_summary_records_skipped_objects(live_org, session, output_base, tmp_path):
    """Summary JSON must exist and list skipped objects (if any)."""
    config = load_config()
    req = TechnicalRequest(
        only=["ApexClass", "limits", "recordCount"],
        limit=5,
        plan_path=None,
        dry_run=False,
    )
    with audit_log(live_org, log_dir=tmp_path / "logs") as log:
        publish_path = execute(session, output_base, req, config.temp_root, log)

    summary = json.loads((publish_path / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert "objects" in summary
    assert "skipped" in summary
    assert isinstance(summary["objects"], list)
    assert isinstance(summary["skipped"], list)
